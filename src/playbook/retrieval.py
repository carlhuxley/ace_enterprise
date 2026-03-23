"""
Fine-Grained Retrieval Engine for Playbook Bullets.
Based on PRD Section 4.3: Fine-Grained Retrieval
"""
import logging

import numpy as np

from src.config.settings import settings
from src.storage.schemas import Bullet

logger = logging.getLogger(__name__)


class BulletRetriever:
    """
    Hybrid retrieval system for selecting relevant bullets.

    Features (PRD Section 4.3):
    - Semantic similarity (embeddings)
    - Keyword matching (BM25)
    - Helpful/harmful ratio filtering
    - Configurable top-k
    - Section-aware retrieval
    - Sub-100ms latency target
    """

    def __init__(
        self,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
    ) -> None:
        """
        Initialize retriever.

        Args:
            top_k: Number of bullets to retrieve (default from settings)
            similarity_threshold: Minimum similarity score (default from settings)
        """
        self.top_k = top_k if top_k is not None else settings.retrieval_top_k
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else settings.retrieval_similarity_threshold
        )

    def retrieve(
        self,
        query: str,
        bullets: list[Bullet],
        query_embedding: list[float] | None = None,
        filter_section: str | None = None,
        min_helpful_ratio: float | None = None,
        min_confidence: float = 0.5,
        domain: str | None = None,
        project_id: str | None = None,
    ) -> list[tuple[Bullet, float]]:
        """
        Retrieve most relevant bullets for a query.

        Uses hybrid approach:
        1. Semantic similarity (if embeddings available)
        2. Keyword matching (BM25-style)
        3. Helpful/harmful ratio boost

        Args:
            query: Query text
            bullets: List of candidate bullets
            query_embedding: Pre-computed query embedding (optional)
            filter_section: Only retrieve from specific section (optional)
            min_helpful_ratio: Minimum helpful/(helpful+harmful) ratio (optional)
            min_confidence: Minimum confidence_score threshold (default 0.5)
            domain: Only retrieve bullets applicable to this domain (optional)
            project_id: Only retrieve bullets applicable to this project (optional)

        Returns:
            List of (bullet, score) tuples, sorted by relevance
        """
        if not bullets:
            return []

        # Filter by confidence threshold
        bullets = [
            b for b in bullets
            if getattr(b, 'confidence_score', 0.5) >= min_confidence
        ]

        # Filter by domain if specified
        if domain:
            bullets = [
                b for b in bullets
                if not getattr(b, 'applicable_domains', None)
                or domain in (b.applicable_domains or [])
            ]

        # Filter by project if specified
        if project_id:
            bullets = [
                b for b in bullets
                if not getattr(b, 'project_ids', None)
                or project_id in (b.project_ids or [])
            ]

        # Filter by section if requested
        if filter_section:
            bullets = [b for b in bullets if b.section == filter_section]

        # Filter by helpful ratio if requested
        if min_helpful_ratio is not None:
            bullets = [
                b for b in bullets
                if self._helpful_ratio(b) >= min_helpful_ratio
            ]

        if not bullets:
            return []

        # Score bullets
        scored_bullets = []

        for bullet in bullets:
            score = self._score_bullet(
                query=query,
                bullet=bullet,
                query_embedding=query_embedding,
            )

            # Only include if above threshold
            if score >= self.similarity_threshold:
                scored_bullets.append((bullet, score))

        # Sort by score (descending)
        scored_bullets.sort(key=lambda x: x[1], reverse=True)

        # Return top-k
        result = scored_bullets[:self.top_k]

        logger.debug(
            f"Retrieved {len(result)} bullets from {len(bullets)} candidates "
            f"for query: '{query[:50]}...'"
        )

        return result

    def retrieve_cross_model(
        self,
        query: str,
        primary_bullets: list[Bullet],
        secondary_bullets_by_playbook: dict[str, list[Bullet]],
        primary_playbook_id: str,
        query_embedding: list[float] | None = None,
        secondary_weight: float = 0.5,
        min_confidence: float = 0.5,
        domain: str | None = None,
        project_id: str | None = None,
    ) -> list[tuple[Bullet, float, str]]:
        """
        Retrieve bullets with cross-model learning support.

        Retrieves from primary playbook + other playbooks in same domain,
        with weighted scoring for secondary sources.

        Args:
            query: Query text
            primary_bullets: Bullets from the primary (model-specific) playbook
            secondary_bullets_by_playbook: Dict mapping playbook_id to bullets from other models
            primary_playbook_id: ID of the primary playbook (for source tracking)
            query_embedding: Pre-computed query embedding (optional)
            secondary_weight: Weight multiplier for secondary playbook bullets (0-1)
            min_confidence: Minimum confidence_score threshold (default 0.5)
            domain: Only retrieve bullets applicable to this domain (optional)
            project_id: Only retrieve bullets applicable to this project (optional)

        Returns:
            List of (bullet, score, source_playbook_id) tuples, sorted by relevance
        """
        # Apply context filters to primary bullets
        primary_bullets = self._filter_by_context(
            primary_bullets, min_confidence, domain, project_id
        )

        # Apply context filters to secondary bullets
        for playbook_id in list(secondary_bullets_by_playbook.keys()):
            secondary_bullets_by_playbook[playbook_id] = self._filter_by_context(
                secondary_bullets_by_playbook[playbook_id],
                min_confidence,
                domain,
                project_id,
            )

        scored_bullets = []

        # Score primary bullets (full weight)
        for bullet in primary_bullets:
            score = self._score_bullet(
                query=query,
                bullet=bullet,
                query_embedding=query_embedding,
            )
            if score >= self.similarity_threshold:
                scored_bullets.append((bullet, score, primary_playbook_id))

        # Score secondary bullets (weighted)
        for playbook_id, bullets in secondary_bullets_by_playbook.items():
            for bullet in bullets:
                score = self._score_bullet(
                    query=query,
                    bullet=bullet,
                    query_embedding=query_embedding,
                )

                # Check threshold BEFORE weighting for secondary bullets
                # This ensures good matches from other models aren't excluded just because of lower weight
                if score >= self.similarity_threshold:
                    # Apply secondary weight for ranking
                    weighted_score = score * secondary_weight
                    scored_bullets.append((bullet, weighted_score, playbook_id))

        # Sort by score (descending)
        scored_bullets.sort(key=lambda x: x[1], reverse=True)

        # Return top-k
        result = scored_bullets[:self.top_k]

        logger.debug(
            f"Cross-model retrieval: {len(result)} bullets "
            f"({sum(1 for _, _, src in result if src == primary_playbook_id)} primary, "
            f"{sum(1 for _, _, src in result if src != primary_playbook_id)} secondary)"
        )

        return result

    def retrieve_by_ids(
        self,
        bullet_ids: list[str],
        bullets: list[Bullet],
    ) -> list[Bullet]:
        """
        Retrieve specific bullets by their IDs.

        Args:
            bullet_ids: List of bullet IDs to retrieve
            bullets: List of candidate bullets

        Returns:
            List of bullets matching the IDs (in order)
        """
        bullet_map = {b.id: b for b in bullets}
        result = []

        for bullet_id in bullet_ids:
            if bullet_id in bullet_map:
                result.append(bullet_map[bullet_id])
            else:
                logger.warning(f"Bullet {bullet_id} not found")

        return result

    def _score_bullet(
        self,
        query: str,
        bullet: Bullet,
        query_embedding: list[float] | None,
    ) -> float:
        """
        Calculate relevance score for a bullet.

        Combines:
        - Semantic similarity (0-1)
        - Keyword match score (0-1)
        - Helpful ratio boost (0-0.2)

        Args:
            query: Query text
            bullet: Bullet to score
            query_embedding: Query embedding (if available)

        Returns:
            Combined relevance score
        """
        # 1. Semantic similarity (weight: 0.6)
        semantic_score = 0.0
        if query_embedding and bullet.embedding:
            semantic_score = self._cosine_similarity(query_embedding, bullet.embedding)

        # 2. Keyword match (weight: 0.3)
        keyword_score = self._keyword_match(query, bullet.content)

        # 3. Helpful ratio boost (weight: 0.1)
        ratio_boost = self._helpful_ratio(bullet) * 0.1

        # Combine scores
        if semantic_score > 0:
            # Semantic + keyword + boost
            total_score = (semantic_score * 0.6) + (keyword_score * 0.3) + ratio_boost
        else:
            # Keyword only + boost (no embeddings available)
            total_score = (keyword_score * 0.9) + ratio_boost

        return total_score

    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        v1 = np.array(vec1)
        v2 = np.array(vec2)

        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(v1, v2) / (norm1 * norm2))

    @staticmethod
    def _keyword_match(query: str, content: str) -> float:
        """
        Simple keyword matching score (BM25-style).

        Calculates percentage of query words found in content.

        Args:
            query: Query text
            content: Bullet content

        Returns:
            Match score (0-1)
        """
        # Tokenize and normalize
        query_words = set(query.lower().split())
        content_words = set(content.lower().split())

        if not query_words:
            return 0.0

        # Calculate overlap
        matches = query_words & content_words
        score = len(matches) / len(query_words)

        return score

    @staticmethod
    def _helpful_ratio(bullet: Bullet) -> float:
        """Calculate helpful/(helpful+harmful) ratio."""
        total = bullet.helpful_count + bullet.harmful_count
        if total == 0:
            return 0.5  # Neutral for bullets with no feedback
        return bullet.helpful_count / total

    @staticmethod
    def _filter_by_context(
        bullets: list[Bullet],
        min_confidence: float = 0.5,
        domain: str | None = None,
        project_id: str | None = None,
    ) -> list[Bullet]:
        """
        Filter bullets by confidence threshold and context.

        Args:
            bullets: List of bullets to filter
            min_confidence: Minimum confidence_score threshold
            domain: Only include bullets applicable to this domain
            project_id: Only include bullets applicable to this project

        Returns:
            Filtered list of bullets
        """
        filtered = bullets

        # Filter by confidence threshold
        filtered = [
            b for b in filtered
            if getattr(b, 'confidence_score', 0.5) >= min_confidence
        ]

        # Filter by domain if specified
        if domain:
            filtered = [
                b for b in filtered
                if not getattr(b, 'applicable_domains', None)
                or domain in (b.applicable_domains or [])
            ]

        # Filter by project if specified
        if project_id:
            filtered = [
                b for b in filtered
                if not getattr(b, 'project_ids', None)
                or project_id in (b.project_ids or [])
            ]

        return filtered

    def get_section_distribution(
        self,
        retrieved: list[tuple[Bullet, float]],
    ) -> dict[str, int]:
        """
        Get distribution of retrieved bullets by section.

        Args:
            retrieved: List of (bullet, score) tuples

        Returns:
            Dictionary mapping section name to count
        """
        distribution: dict[str, int] = {}

        for bullet, _ in retrieved:
            distribution[bullet.section] = distribution.get(bullet.section, 0) + 1

        return distribution

    def filter_by_tags(
        self,
        bullets: list[Bullet],
        required_tags: list[str] | None = None,
        excluded_tags: list[str] | None = None,
    ) -> list[Bullet]:
        """
        Filter bullets by tags.

        Args:
            bullets: List of bullets to filter
            required_tags: Tags that must be present (OR logic)
            excluded_tags: Tags that must not be present

        Returns:
            Filtered list of bullets
        """
        filtered = bullets

        # Filter by required tags (OR logic)
        if required_tags:
            filtered = [
                b for b in filtered
                if any(tag in b.tags for tag in required_tags)
            ]

        # Filter by excluded tags
        if excluded_tags:
            filtered = [
                b for b in filtered
                if not any(tag in b.tags for tag in excluded_tags)
            ]

        return filtered

    def rerank_by_recency(
        self,
        bullets: list[tuple[Bullet, float]],
        recency_weight: float = 0.1,
    ) -> list[tuple[Bullet, float]]:
        """
        Re-rank bullets with recency boost.

        Args:
            bullets: List of (bullet, score) tuples
            recency_weight: Weight for recency boost (0-1)

        Returns:
            Re-ranked list
        """
        if not bullets:
            return bullets

        # Find most recent timestamp
        max_timestamp = max(
            bullet.created_at.timestamp()
            for bullet, _ in bullets
        )

        # Re-score with recency
        reranked = []
        for bullet, score in bullets:
            # Normalize recency (0-1)
            recency = bullet.created_at.timestamp() / max_timestamp

            # Add recency boost
            new_score = score + (recency * recency_weight)
            reranked.append((bullet, new_score))

        # Re-sort
        reranked.sort(key=lambda x: x[1], reverse=True)

        return reranked
