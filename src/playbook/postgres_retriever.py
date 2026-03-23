"""
PostgreSQL-backed Bullet Retriever using pgvector.

Replaces in-memory retrieval with PostgreSQL vector similarity search.
"""
import logging

from src.config.settings import settings
from src.playbook.postgres_adapter import PostgresPlaybookAdapter
from src.storage.schemas import Bullet

logger = logging.getLogger(__name__)


class PostgresBulletRetriever:
    """
    PostgreSQL-backed retrieval system using pgvector.

    Features:
    - Semantic similarity via pgvector (fast!)
    - Helpful/harmful ratio filtering
    - Section-aware retrieval
    - Direct database queries (no loading all bullets into memory)
    """

    def __init__(
        self,
        playbook_adapter: PostgresPlaybookAdapter,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
    ) -> None:
        """
        Initialize PostgreSQL retriever.

        Args:
            playbook_adapter: PostgreSQL playbook adapter
            top_k: Number of bullets to retrieve (default from settings)
            similarity_threshold: Minimum similarity score (default from settings)
        """
        self.adapter = playbook_adapter
        self.top_k = top_k if top_k is not None else settings.retrieval_top_k
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else settings.retrieval_similarity_threshold
        )

    def retrieve(
        self,
        query: str,
        playbook_id: str | None = None,
        filter_section: str | None = None,
        min_helpful_ratio: float | None = None,
        top_k: int | None = None,
        min_confidence: float = 0.5,
        domain: str | None = None,
        project_id: str | None = None,
    ) -> list[tuple[Bullet, float]]:
        """
        Retrieve most relevant bullets using PostgreSQL vector search.

        Args:
            query: Query text
            playbook_id: Optional playbook to search within
            filter_section: Only retrieve from specific section (optional)
            min_helpful_ratio: Minimum helpful/(helpful+harmful) ratio (optional)
            top_k: Override default top_k
            min_confidence: Minimum confidence_score threshold (default 0.5)
            domain: Only retrieve bullets applicable to this domain (optional)
            project_id: Only retrieve bullets applicable to this project (optional)

        Returns:
            List of (bullet, score) tuples, sorted by relevance
        """
        # Use PostgreSQL semantic search
        results = self.adapter.semantic_search(
            query=query,
            playbook_id=playbook_id,
            top_k=top_k or self.top_k,
            similarity_threshold=self.similarity_threshold,
        )

        # Filter by confidence threshold
        results = [
            (bullet, score)
            for bullet, score in results
            if getattr(bullet, 'confidence_score', 0.5) >= min_confidence
        ]

        # Filter by domain if specified
        if domain:
            results = [
                (bullet, score)
                for bullet, score in results
                if not getattr(bullet, 'applicable_domains', None)
                or domain in (bullet.applicable_domains or [])
            ]

        # Filter by project if specified
        if project_id:
            results = [
                (bullet, score)
                for bullet, score in results
                if not getattr(bullet, 'project_ids', None)
                or project_id in (bullet.project_ids or [])
            ]

        # Filter by section if requested
        if filter_section:
            results = [
                (bullet, score)
                for bullet, score in results
                if bullet.section == filter_section
            ]

        # Filter by helpful ratio if requested
        if min_helpful_ratio is not None:
            results = [
                (bullet, score)
                for bullet, score in results
                if self._helpful_ratio(bullet) >= min_helpful_ratio
            ]

        logger.debug(f"Retrieved {len(results)} bullets for query: {query[:50]}...")

        return results

    def retrieve_from_bullets(
        self,
        query: str,
        bullets: list[Bullet],
        query_embedding: list[float] | None = None,
        filter_section: str | None = None,
        min_helpful_ratio: float | None = None,
    ) -> list[tuple[Bullet, float]]:
        """
        Retrieve from a pre-filtered list of bullets (fallback to in-memory).

        This method is kept for backwards compatibility but is less efficient
        than using the database directly.

        Args:
            query: Query text
            bullets: Pre-filtered list of bullets
            query_embedding: Pre-computed query embedding (ignored)
            filter_section: Only retrieve from specific section (optional)
            min_helpful_ratio: Minimum helpful/(helpful+harmful) ratio (optional)

        Returns:
            List of (bullet, score) tuples, sorted by relevance
        """
        # For now, just use the database retrieval
        # This is less efficient but maintains compatibility
        logger.warning(
            "retrieve_from_bullets() is deprecated when using PostgreSQL. "
            "Use retrieve() instead for better performance."
        )

        # Fall back to database search
        return self.retrieve(
            query=query,
            filter_section=filter_section,
            min_helpful_ratio=min_helpful_ratio,
        )

    def _helpful_ratio(self, bullet: Bullet) -> float:
        """Calculate helpful ratio for a bullet."""
        total = bullet.helpful_count + bullet.harmful_count
        if total == 0:
            return 0.5  # Neutral for untested bullets
        return bullet.helpful_count / total
