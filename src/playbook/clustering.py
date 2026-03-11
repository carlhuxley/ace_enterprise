"""
DBSCAN Clustering for Playbook Bullets.

Implements prompt-level distillation via density-based clustering.
Based on: https://arxiv.org/pdf/2602.21103v1

This module complements ensemble voting:
- DBSCAN answers: "What categories of knowledge exist?"
- Ensemble voting answers: "Which knowledge is correct?"

Together they produce diverse, high-quality distillation sets.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import cosine_distances

from src.storage.schemas import Bullet

logger = logging.getLogger(__name__)


class RepresentativeStrategy(str, Enum):
    """Strategy for selecting cluster representatives."""

    HIGHEST_HELPFUL = "highest_helpful"  # Best helpful/harmful ratio
    MOST_CENTRAL = "most_central"  # Closest to cluster centroid
    MOST_RECENT = "most_recent"  # Most recently created
    ENSEMBLE = "ensemble"  # Defer to ensemble voting


@dataclass
class BulletCluster:
    """A cluster of semantically related bullets."""

    cluster_id: int
    bullets: list[Bullet]
    centroid: np.ndarray | None = None
    representative: Bullet | None = None
    representative_strategy: RepresentativeStrategy | None = None

    @property
    def size(self) -> int:
        return len(self.bullets)

    @property
    def avg_helpful_ratio(self) -> float:
        """Average helpful ratio across cluster."""
        ratios = []
        for b in self.bullets:
            total = b.helpful_count + b.harmful_count
            if total > 0:
                ratios.append(b.helpful_count / total)
        return sum(ratios) / len(ratios) if ratios else 0.5

    @property
    def models_represented(self) -> set[str]:
        """Unique models that contributed to this cluster."""
        return {b.created_by_model for b in self.bullets if b.created_by_model}


@dataclass
class ClusteringResult:
    """Result of DBSCAN clustering operation."""

    clusters: list[BulletCluster]
    outliers: list[Bullet]  # Noise points (cluster_id = -1)
    n_clusters: int
    n_outliers: int
    eps: float
    min_samples: int

    # Distillation set (one representative per cluster)
    distillation_set: list[Bullet] = field(default_factory=list)

    @property
    def coverage_by_model(self) -> dict[str, int]:
        """How many clusters each model contributed to."""
        coverage: dict[str, int] = {}
        for cluster in self.clusters:
            for model in cluster.models_represented:
                coverage[model] = coverage.get(model, 0) + 1
        return coverage


class BulletClusterer:
    """
    DBSCAN-based clustering for playbook bullets.

    Uses density-based clustering to group semantically related bullets,
    enabling diverse representative selection for prompt-level distillation.

    Key differences from BulletDeduplicator:
    - Deduplicator: Binary decision (duplicate or not) at high threshold (0.85)
    - Clusterer: Groups related bullets at lower threshold, finds natural clusters

    Usage:
        clusterer = BulletClusterer(eps=0.3, min_samples=2)
        result = clusterer.cluster(bullets)

        # Get diverse distillation set
        distillation_bullets = result.distillation_set

        # Review outliers (unique knowledge or potential errors)
        outliers = result.outliers
    """

    def __init__(
        self,
        eps: float = 0.3,
        min_samples: int = 2,
        representative_strategy: RepresentativeStrategy = RepresentativeStrategy.HIGHEST_HELPFUL,
    ) -> None:
        """
        Initialize clusterer.

        Args:
            eps: Maximum distance between points in a cluster.
                 Lower = tighter clusters, more outliers.
                 For cosine distance: 0.3 = ~0.7 similarity threshold.
            min_samples: Minimum points to form a cluster.
                         Higher = fewer, denser clusters.
            representative_strategy: How to pick cluster representatives.
        """
        self.eps = eps
        self.min_samples = min_samples
        self.representative_strategy = representative_strategy

    def cluster(
        self,
        bullets: list[Bullet],
        strategy: RepresentativeStrategy | None = None,
    ) -> ClusteringResult:
        """
        Cluster bullets using DBSCAN.

        Args:
            bullets: Bullets to cluster (must have embeddings)
            strategy: Override default representative strategy

        Returns:
            ClusteringResult with clusters, outliers, and distillation set
        """
        if not bullets:
            return ClusteringResult(
                clusters=[],
                outliers=[],
                n_clusters=0,
                n_outliers=0,
                eps=self.eps,
                min_samples=self.min_samples,
            )

        strategy = strategy or self.representative_strategy

        # Filter to bullets with embeddings
        bullets_with_embeddings = [b for b in bullets if b.embedding is not None]
        bullets_without_embeddings = [b for b in bullets if b.embedding is None]

        if bullets_without_embeddings:
            logger.warning(
                f"{len(bullets_without_embeddings)} bullets lack embeddings, "
                "treating as outliers"
            )

        if not bullets_with_embeddings:
            return ClusteringResult(
                clusters=[],
                outliers=bullets,
                n_clusters=0,
                n_outliers=len(bullets),
                eps=self.eps,
                min_samples=self.min_samples,
            )

        # Build embedding matrix
        embeddings = np.array([b.embedding for b in bullets_with_embeddings])

        # Compute cosine distance matrix (DBSCAN needs distance, not similarity)
        # cosine_distance = 1 - cosine_similarity
        distance_matrix = cosine_distances(embeddings)

        # Run DBSCAN with precomputed distances
        dbscan = DBSCAN(
            eps=self.eps,
            min_samples=self.min_samples,
            metric="precomputed",
        )
        labels = dbscan.fit_predict(distance_matrix)

        # Group bullets by cluster
        cluster_map: dict[int, list[tuple[Bullet, np.ndarray]]] = {}
        outliers: list[Bullet] = list(bullets_without_embeddings)  # Start with no-embedding bullets

        for bullet, embedding, label in zip(bullets_with_embeddings, embeddings, labels):
            if label == -1:
                outliers.append(bullet)
            else:
                if label not in cluster_map:
                    cluster_map[label] = []
                cluster_map[label].append((bullet, embedding))

        # Build BulletCluster objects
        clusters: list[BulletCluster] = []
        for cluster_id, bullet_embedding_pairs in sorted(cluster_map.items()):
            cluster_bullets = [b for b, _ in bullet_embedding_pairs]
            cluster_embeddings = np.array([e for _, e in bullet_embedding_pairs])

            # Compute centroid
            centroid = cluster_embeddings.mean(axis=0)

            cluster = BulletCluster(
                cluster_id=cluster_id,
                bullets=cluster_bullets,
                centroid=centroid,
            )

            # Select representative
            if strategy != RepresentativeStrategy.ENSEMBLE:
                representative = self._select_representative(
                    cluster_bullets,
                    cluster_embeddings,
                    centroid,
                    strategy,
                )
                cluster.representative = representative
                cluster.representative_strategy = strategy

            clusters.append(cluster)

        # Build distillation set
        distillation_set = [
            c.representative for c in clusters if c.representative is not None
        ]

        n_clusters = len(clusters)
        n_outliers = len(outliers)

        logger.info(
            f"DBSCAN clustering: {len(bullets)} bullets -> "
            f"{n_clusters} clusters + {n_outliers} outliers "
            f"(eps={self.eps}, min_samples={self.min_samples})"
        )

        return ClusteringResult(
            clusters=clusters,
            outliers=outliers,
            n_clusters=n_clusters,
            n_outliers=n_outliers,
            eps=self.eps,
            min_samples=self.min_samples,
            distillation_set=distillation_set,
        )

    def _select_representative(
        self,
        bullets: list[Bullet],
        embeddings: np.ndarray,
        centroid: np.ndarray,
        strategy: RepresentativeStrategy,
    ) -> Bullet:
        """Select the best representative bullet from a cluster."""
        if len(bullets) == 1:
            return bullets[0]

        if strategy == RepresentativeStrategy.HIGHEST_HELPFUL:
            return self._select_by_helpful_ratio(bullets)

        elif strategy == RepresentativeStrategy.MOST_CENTRAL:
            return self._select_by_centrality(bullets, embeddings, centroid)

        elif strategy == RepresentativeStrategy.MOST_RECENT:
            return self._select_by_recency(bullets)

        else:
            # Fallback to helpful ratio
            return self._select_by_helpful_ratio(bullets)

    def _select_by_helpful_ratio(self, bullets: list[Bullet]) -> Bullet:
        """Select bullet with best helpful/harmful ratio, breaking ties with count."""

        def helpful_score(b: Bullet) -> tuple[float, int]:
            total = b.helpful_count + b.harmful_count
            if total == 0:
                ratio = 0.5  # Neutral
            else:
                ratio = b.helpful_count / total
            # Return tuple: (ratio, helpful_count) - ties broken by absolute count
            return (ratio, b.helpful_count)

        return max(bullets, key=helpful_score)

    def _select_by_centrality(
        self,
        bullets: list[Bullet],
        embeddings: np.ndarray,
        centroid: np.ndarray,
    ) -> Bullet:
        """Select bullet closest to cluster centroid."""
        distances = cosine_distances([centroid], embeddings)[0]
        min_idx = int(np.argmin(distances))
        return bullets[min_idx]

    def _select_by_recency(self, bullets: list[Bullet]) -> Bullet:
        """Select most recently created bullet."""
        return max(bullets, key=lambda b: b.created_at)

    def cluster_by_model_strength(
        self,
        bullets: list[Bullet],
        model_weights: dict[str, float],
        min_weight: float = 1.0,
    ) -> ClusteringResult:
        """
        Cluster bullets, filtering to strong models only.

        For distillation: only use knowledge from models above a quality threshold.

        Args:
            bullets: All bullets to consider
            model_weights: Model ID -> voting weight mapping
            min_weight: Minimum weight to include (default 1.0 = average)

        Returns:
            ClusteringResult from strong model bullets only
        """
        # Filter to bullets from strong models
        strong_bullets = []
        weak_bullets = []

        for bullet in bullets:
            model = bullet.created_by_model
            weight = model_weights.get(model, 1.0) if model else 1.0

            if weight >= min_weight:
                strong_bullets.append(bullet)
            else:
                weak_bullets.append(bullet)

        logger.info(
            f"Filtering by model strength: {len(strong_bullets)} strong, "
            f"{len(weak_bullets)} weak (threshold={min_weight})"
        )

        # Cluster strong bullets only
        return self.cluster(strong_bullets)

    def find_knowledge_gaps(
        self,
        strong_result: ClusteringResult,
        weak_bullets: list[Bullet],
    ) -> list[Bullet]:
        """
        Find knowledge that weak models have but strong models don't.

        These might be:
        - Novel insights from weak models worth reviewing
        - Errors/hallucinations unique to weak models
        - Domain expertise the weak model has

        Args:
            strong_result: Clustering result from strong model bullets
            weak_bullets: Bullets from weak models

        Returns:
            Weak model bullets that don't match any strong model cluster
        """
        if not weak_bullets:
            return []

        weak_with_embeddings = [b for b in weak_bullets if b.embedding is not None]
        if not weak_with_embeddings:
            return weak_bullets

        # Get all strong model centroids
        centroids = [c.centroid for c in strong_result.clusters if c.centroid is not None]
        if not centroids:
            return weak_bullets  # No clusters to compare against

        centroid_matrix = np.array(centroids)

        # Find weak bullets that are far from all centroids
        gaps = []
        for bullet in weak_with_embeddings:
            embedding = np.array(bullet.embedding).reshape(1, -1)
            distances = cosine_distances(embedding, centroid_matrix)[0]

            # If far from all centroids, it's a gap
            min_distance = distances.min()
            if min_distance > self.eps:
                gaps.append(bullet)

        logger.info(
            f"Found {len(gaps)} knowledge gaps in weak model bullets "
            f"(not covered by {len(centroids)} strong model clusters)"
        )

        return gaps


def build_distillation_playbook(
    bullets: list[Bullet],
    model_weights: dict[str, float] | None = None,
    eps: float = 0.3,
    min_samples: int = 2,
    min_model_weight: float = 1.0,
    strategy: RepresentativeStrategy = RepresentativeStrategy.HIGHEST_HELPFUL,
) -> tuple[list[Bullet], ClusteringResult]:
    """
    Build a distillation playbook from accumulated knowledge.

    This is the main entry point for prompt-level distillation.

    Args:
        bullets: All bullets to consider
        model_weights: Optional model strength weights
        eps: DBSCAN eps parameter
        min_samples: DBSCAN min_samples parameter
        min_model_weight: Minimum model weight to include
        strategy: Representative selection strategy

    Returns:
        Tuple of (distillation_bullets, full_clustering_result)

    Example:
        # Get bullets from all playbooks
        all_bullets = playbook_manager.get_all_bullets()

        # Get model weights from ensemble performance
        model_weights = {
            "gpt-4o": 1.8,
            "claude-3-opus": 1.7,
            "qwen2.5-72b": 1.2,
            "qwen2.5-7b": 0.8,  # Will be filtered out
        }

        # Build distillation set
        distillation_bullets, result = build_distillation_playbook(
            bullets=all_bullets,
            model_weights=model_weights,
            min_model_weight=1.0,
        )

        # Inject into weak model prompts
        weak_model_context = format_bullets_as_context(distillation_bullets)
    """
    clusterer = BulletClusterer(
        eps=eps,
        min_samples=min_samples,
        representative_strategy=strategy,
    )

    if model_weights:
        result = clusterer.cluster_by_model_strength(
            bullets=bullets,
            model_weights=model_weights,
            min_weight=min_model_weight,
        )
    else:
        result = clusterer.cluster(bullets)

    return result.distillation_set, result
