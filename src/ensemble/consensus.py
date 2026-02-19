"""
Consensus building for ensemble learning.

Handles:
- Clustering similar bullets from different models
- Deduplicating redundant proposals
- Merging similar bullets into consensus versions
- Analyzing diversity and agreement
"""
import logging
import uuid
from collections import defaultdict

from src.ensemble.models import (
    ConsensusBullet,
)
from src.utils.embedding import get_embedding_service

logger = logging.getLogger(__name__)


class ConsensusBuilder:
    """
    Build consensus from multiple model proposals.

    Clusters similar bullets and identifies unique contributions.
    """

    def __init__(self, similarity_threshold: float = 0.85):
        """
        Args:
            similarity_threshold: Cosine similarity threshold for clustering (0.0-1.0)
        """
        self.similarity_threshold = similarity_threshold
        self.embedding_service = get_embedding_service()

    def cluster_bullets(
        self, bullets: list[ConsensusBullet]
    ) -> dict[str, list[ConsensusBullet]]:
        """
        Cluster similar bullets together.

        Args:
            bullets: List of proposed bullets

        Returns:
            Dict mapping cluster_id -> list of bullets in that cluster
        """
        if not bullets:
            return {}

        # Generate embeddings for all bullets
        bullet_texts = [b.content for b in bullets]
        embeddings = self.embedding_service.embed_batch(bullet_texts)

        # Assign embeddings to bullets
        for bullet, embedding in zip(bullets, embeddings):
            bullet._embedding = embedding  # Temporary storage

        # Greedy clustering
        clusters: dict[str, list[ConsensusBullet]] = {}
        assigned = set()

        for i, bullet in enumerate(bullets):
            if i in assigned:
                continue

            # Create new cluster
            cluster_id = str(uuid.uuid4())[:8]
            cluster = [bullet]
            bullet.cluster_id = cluster_id
            assigned.add(i)

            # Find similar bullets
            for j, other_bullet in enumerate(bullets):
                if j in assigned or i == j:
                    continue

                similarity = self._cosine_similarity(
                    bullet._embedding, other_bullet._embedding
                )

                if similarity >= self.similarity_threshold:
                    cluster.append(other_bullet)
                    other_bullet.cluster_id = cluster_id
                    other_bullet.similar_bullets.append(bullet.content[:50])
                    assigned.add(j)

            clusters[cluster_id] = cluster

        logger.info(
            f"Clustered {len(bullets)} bullets into {len(clusters)} clusters "
            f"(threshold: {self.similarity_threshold})"
        )

        return clusters

    def build_consensus(
        self, bullets: list[ConsensusBullet]
    ) -> list[ConsensusBullet]:
        """
        Build consensus bullets from clusters.

        For each cluster:
        - If all bullets identical -> keep one
        - If bullets similar -> merge into best version
        - Track which models proposed similar ideas

        Args:
            bullets: List of proposed bullets

        Returns:
            Deduplicated list of consensus bullets
        """
        clusters = self.cluster_bullets(bullets)

        consensus_bullets = []

        for cluster_id, cluster_bullets in clusters.items():
            if len(cluster_bullets) == 1:
                # Unique bullet, keep as-is
                consensus_bullets.append(cluster_bullets[0])
            else:
                # Multiple similar bullets, merge
                merged = self._merge_cluster(cluster_bullets)
                consensus_bullets.append(merged)

        logger.info(
            f"Built consensus: {len(bullets)} proposals -> "
            f"{len(consensus_bullets)} unique bullets"
        )

        return consensus_bullets

    def _merge_cluster(
        self, cluster_bullets: list[ConsensusBullet]
    ) -> ConsensusBullet:
        """
        Merge similar bullets into best representative.

        Strategy:
        1. Pick longest/most detailed version as base
        2. Track all proposing models
        3. Combine tags
        4. Note in reasoning that this is merged

        Args:
            cluster_bullets: Bullets in the same cluster

        Returns:
            Merged consensus bullet
        """
        # Pick longest bullet as most detailed
        base_bullet = max(cluster_bullets, key=lambda b: len(b.content))

        # Collect all proposing models
        proposers = [b.proposed_by for b in cluster_bullets]

        # Combine tags
        all_tags = set()
        for bullet in cluster_bullets:
            all_tags.update(bullet.tags)

        # Create merged bullet
        merged = ConsensusBullet(
            content=base_bullet.content,
            section=base_bullet.section,
            tags=sorted(all_tags),
            proposed_by=f"consensus_{len(proposers)}",
            proposal_reasoning=(
                f"Merged from {len(proposers)} similar proposals: {', '.join(proposers)}. "
                f"Original: {base_bullet.proposal_reasoning}"
            ),
            cluster_id=base_bullet.cluster_id,
        )

        # Track similar bullets
        merged.similar_bullets = [b.content[:50] for b in cluster_bullets if b != base_bullet]

        logger.debug(
            f"Merged {len(cluster_bullets)} bullets: {merged.content[:50]}..."
        )

        return merged

    def calculate_diversity_score(self, bullets: list[ConsensusBullet]) -> float:
        """
        Calculate how diverse the proposals are.

        Low diversity = many similar bullets (lots of agreement)
        High diversity = unique bullets (independent thinking)

        Args:
            bullets: List of bullets to analyze

        Returns:
            Diversity score 0.0-1.0 (1.0 = maximum diversity)
        """
        if not bullets:
            return 0.0

        clusters = self.cluster_bullets(bullets)

        # Diversity = proportion of unique clusters
        diversity = len(clusters) / len(bullets)

        logger.debug(
            f"Diversity: {len(clusters)} unique / {len(bullets)} total = {diversity:.2f}"
        )

        return diversity

    def calculate_consensus_strength(
        self, bullets: list[ConsensusBullet]
    ) -> float:
        """
        Calculate how strong the consensus is.

        Strong consensus = high approval rates, low disagreement
        Weak consensus = split votes, lots of disagreement

        Args:
            bullets: Voted bullets to analyze

        Returns:
            Consensus strength 0.0-1.0 (1.0 = perfect agreement)
        """
        if not bullets:
            return 0.0

        # Calculate average approval rate across all bullets
        approval_rates = [b.approval_rate for b in bullets if b.votes]

        if not approval_rates:
            return 0.0

        avg_approval = sum(approval_rates) / len(approval_rates)

        # Also factor in variance - low variance = strong consensus
        variance = sum((r - avg_approval) ** 2 for r in approval_rates) / len(
            approval_rates
        )

        # Consensus strength = high approval + low variance
        # Normalize variance to 0-1 range (max variance is 0.25 when rates are 0 and 1)
        normalized_variance = min(variance / 0.25, 1.0)
        consensus_strength = avg_approval * (1 - normalized_variance)

        logger.debug(
            f"Consensus strength: {consensus_strength:.2f} "
            f"(avg approval: {avg_approval:.2f}, variance: {variance:.3f})"
        )

        return consensus_strength

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        import math

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    def get_unique_contributions(
        self, bullets: list[ConsensusBullet]
    ) -> dict[str, list[ConsensusBullet]]:
        """
        Identify which bullets each model uniquely contributed.

        Args:
            bullets: All consensus bullets

        Returns:
            Dict mapping model_id -> unique bullets only that model proposed
        """
        clusters = self.cluster_bullets(bullets)

        unique_by_model: dict[str, list[ConsensusBullet]] = defaultdict(list)

        for cluster in clusters.values():
            # If cluster has only 1 bullet, it's unique
            if len(cluster) == 1:
                bullet = cluster[0]
                unique_by_model[bullet.proposed_by].append(bullet)

        logger.info(
            f"Unique contributions: "
            f"{', '.join(f'{model}: {len(bullets)}' for model, bullets in unique_by_model.items())}"
        )

        return dict(unique_by_model)

    def get_agreement_matrix(
        self, bullets: list[ConsensusBullet]
    ) -> dict[tuple[str, str], float]:
        """
        Calculate pairwise agreement between models.

        Args:
            bullets: Voted bullets

        Returns:
            Dict mapping (model1, model2) -> agreement_rate
        """
        # Collect all models
        models = set()
        for bullet in bullets:
            models.add(bullet.proposed_by)
            for vote in bullet.votes:
                models.add(vote.model_id)

        models = sorted(models)

        # Calculate pairwise agreement
        agreement_matrix = {}

        for i, model1 in enumerate(models):
            for model2 in models[i + 1 :]:
                # Find bullets where both voted
                agreements = 0
                total = 0

                for bullet in bullets:
                    vote1 = next((v for v in bullet.votes if v.model_id == model1), None)
                    vote2 = next((v for v in bullet.votes if v.model_id == model2), None)

                    if vote1 and vote2:
                        total += 1
                        if vote1.vote == vote2.vote:
                            agreements += 1

                if total > 0:
                    agreement_rate = agreements / total
                    agreement_matrix[(model1, model2)] = agreement_rate

        logger.debug(
            f"Agreement matrix calculated for {len(models)} models, "
            f"{len(agreement_matrix)} pairs"
        )

        return agreement_matrix
