"""Tests for DBSCAN clustering module - prompt-level distillation."""

from datetime import datetime

import numpy as np
import pytest

from src.playbook.clustering import (
    BulletCluster,
    BulletClusterer,
    ClusteringResult,
    RepresentativeStrategy,
    build_distillation_playbook,
)
from src.storage.schemas import Bullet


def make_bullet(
    content: str,
    embedding: list[float] | None = None,
    helpful_count: int = 0,
    harmful_count: int = 0,
    created_by_model: str | None = None,
    created_at: datetime | None = None,
) -> Bullet:
    """Factory for test bullets."""
    return Bullet(
        id=f"test-{hash(content) % 10000}",
        content=content,
        section="strategies_and_hard_rules",
        tags=[],
        embedding=embedding,
        helpful_count=helpful_count,
        harmful_count=harmful_count,
        created_by_model=created_by_model,
        created_at=created_at or datetime.now(),
    )


def make_similar_embeddings(base: list[float], n: int, noise: float = 0.05, seed: int = 42) -> list[list[float]]:
    """Generate n similar embeddings with small noise."""
    rng = np.random.default_rng(seed)
    base_arr = np.array(base)
    embeddings = []
    for _ in range(n):
        noisy = base_arr + rng.standard_normal(len(base)) * noise
        noisy = noisy / np.linalg.norm(noisy)  # Normalize
        embeddings.append(noisy.tolist())
    return embeddings


class TestBulletClusterer:
    """Test DBSCAN clustering functionality."""

    def test_empty_bullets_returns_empty_result(self):
        """Empty input should return empty clusters."""
        clusterer = BulletClusterer()
        result = clusterer.cluster([])

        assert result.n_clusters == 0
        assert result.n_outliers == 0
        assert result.distillation_set == []

    def test_bullets_without_embeddings_are_outliers(self):
        """Bullets lacking embeddings should be treated as outliers."""
        bullets = [
            make_bullet("no embedding 1"),
            make_bullet("no embedding 2"),
        ]

        clusterer = BulletClusterer()
        result = clusterer.cluster(bullets)

        assert result.n_clusters == 0
        assert result.n_outliers == 2
        assert len(result.outliers) == 2

    def test_similar_bullets_cluster_together(self):
        """Semantically similar bullets should form a cluster."""
        # Create base embeddings for two distinct topics
        auth_base = [1.0] + [0.0] * 383  # 384-dim like real embeddings
        test_base = [0.0] * 192 + [1.0] + [0.0] * 191

        # Generate similar embeddings for each topic
        auth_embeddings = make_similar_embeddings(auth_base, 3, noise=0.02)
        test_embeddings = make_similar_embeddings(test_base, 3, noise=0.02)

        bullets = [
            make_bullet("Use OAuth2 for auth", embedding=auth_embeddings[0]),
            make_bullet("Implement JWT tokens", embedding=auth_embeddings[1]),
            make_bullet("Auth middleware pattern", embedding=auth_embeddings[2]),
            make_bullet("Write unit tests first", embedding=test_embeddings[0]),
            make_bullet("Test edge cases", embedding=test_embeddings[1]),
            make_bullet("Mock external services", embedding=test_embeddings[2]),
        ]

        clusterer = BulletClusterer(eps=0.3, min_samples=2)
        result = clusterer.cluster(bullets)

        # Should find 2 clusters
        assert result.n_clusters == 2
        assert len(result.distillation_set) == 2

    def test_distant_bullets_are_outliers(self):
        """Bullets far from any cluster should be outliers."""
        # Create a tight cluster
        base = [1.0] + [0.0] * 383
        cluster_embeddings = make_similar_embeddings(base, 3, noise=0.02)

        # Create a distant outlier
        outlier_embedding = [0.0] * 192 + [1.0] + [0.0] * 191

        bullets = [
            make_bullet("Cluster item 1", embedding=cluster_embeddings[0]),
            make_bullet("Cluster item 2", embedding=cluster_embeddings[1]),
            make_bullet("Cluster item 3", embedding=cluster_embeddings[2]),
            make_bullet("Distant outlier", embedding=outlier_embedding),
        ]

        clusterer = BulletClusterer(eps=0.2, min_samples=2)
        result = clusterer.cluster(bullets)

        assert result.n_clusters == 1
        assert result.n_outliers == 1
        assert result.outliers[0].content == "Distant outlier"

    def test_representative_selection_highest_helpful(self):
        """Should select bullet with best helpful ratio."""
        base = [1.0] + [0.0] * 383
        embeddings = make_similar_embeddings(base, 3, noise=0.02)

        bullets = [
            make_bullet("Low ratio", embedding=embeddings[0], helpful_count=1, harmful_count=9),
            make_bullet("High ratio", embedding=embeddings[1], helpful_count=9, harmful_count=1),
            make_bullet("Medium ratio", embedding=embeddings[2], helpful_count=5, harmful_count=5),
        ]

        clusterer = BulletClusterer(
            eps=0.3,
            min_samples=2,
            representative_strategy=RepresentativeStrategy.HIGHEST_HELPFUL,
        )
        result = clusterer.cluster(bullets)

        assert result.n_clusters == 1
        assert result.distillation_set[0].content == "High ratio"

    def test_representative_selection_most_central(self):
        """Should select bullet closest to centroid."""
        # Create embeddings where middle one is most central
        embeddings = [
            [1.0, 0.1, 0.0] + [0.0] * 381,  # Slightly off
            [1.0, 0.0, 0.0] + [0.0] * 381,  # Most central
            [1.0, -0.1, 0.0] + [0.0] * 381,  # Slightly off other direction
        ]
        # Normalize
        embeddings = [(np.array(e) / np.linalg.norm(e)).tolist() for e in embeddings]

        bullets = [
            make_bullet("Off center 1", embedding=embeddings[0]),
            make_bullet("Central", embedding=embeddings[1]),
            make_bullet("Off center 2", embedding=embeddings[2]),
        ]

        clusterer = BulletClusterer(
            eps=0.3,
            min_samples=2,
            representative_strategy=RepresentativeStrategy.MOST_CENTRAL,
        )
        result = clusterer.cluster(bullets)

        assert result.n_clusters == 1
        assert result.distillation_set[0].content == "Central"

    def test_representative_selection_most_recent(self):
        """Should select most recently created bullet."""
        base = [1.0] + [0.0] * 383
        embeddings = make_similar_embeddings(base, 3, noise=0.02)

        bullets = [
            make_bullet("Old", embedding=embeddings[0], created_at=datetime(2024, 1, 1)),
            make_bullet("Newest", embedding=embeddings[1], created_at=datetime(2025, 1, 1)),
            make_bullet("Middle", embedding=embeddings[2], created_at=datetime(2024, 6, 1)),
        ]

        clusterer = BulletClusterer(
            eps=0.3,
            min_samples=2,
            representative_strategy=RepresentativeStrategy.MOST_RECENT,
        )
        result = clusterer.cluster(bullets)

        assert result.n_clusters == 1
        assert result.distillation_set[0].content == "Newest"


class TestClusterByModelStrength:
    """Test filtering by model quality."""

    def test_filters_weak_models(self):
        """Should only cluster bullets from strong models."""
        base = [1.0] + [0.0] * 383
        embeddings = make_similar_embeddings(base, 4, noise=0.02)

        bullets = [
            make_bullet("Strong 1", embedding=embeddings[0], created_by_model="gpt-4o"),
            make_bullet("Strong 2", embedding=embeddings[1], created_by_model="claude-opus"),
            make_bullet("Weak 1", embedding=embeddings[2], created_by_model="small-model"),
            make_bullet("Weak 2", embedding=embeddings[3], created_by_model="tiny-model"),
        ]

        model_weights = {
            "gpt-4o": 1.8,
            "claude-opus": 1.5,
            "small-model": 0.7,
            "tiny-model": 0.5,
        }

        clusterer = BulletClusterer(eps=0.3, min_samples=2)
        result = clusterer.cluster_by_model_strength(
            bullets=bullets,
            model_weights=model_weights,
            min_weight=1.0,
        )

        # Only strong model bullets should be in cluster
        assert result.n_clusters == 1
        cluster_contents = [b.content for b in result.clusters[0].bullets]
        assert "Strong 1" in cluster_contents
        assert "Strong 2" in cluster_contents
        assert "Weak 1" not in cluster_contents


class TestKnowledgeGaps:
    """Test finding knowledge gaps between strong and weak models."""

    def test_finds_unique_weak_model_knowledge(self):
        """Should identify knowledge weak models have that strong don't."""
        # Strong model cluster
        strong_base = [1.0] + [0.0] * 383
        strong_embeddings = make_similar_embeddings(strong_base, 3, noise=0.02)

        # Weak model with different knowledge
        weak_base = [0.0] * 192 + [1.0] + [0.0] * 191
        weak_embeddings = make_similar_embeddings(weak_base, 2, noise=0.02)

        strong_bullets = [
            make_bullet("Strong topic 1", embedding=strong_embeddings[0], created_by_model="gpt-4"),
            make_bullet("Strong topic 2", embedding=strong_embeddings[1], created_by_model="gpt-4"),
            make_bullet("Strong topic 3", embedding=strong_embeddings[2], created_by_model="gpt-4"),
        ]

        weak_bullets = [
            make_bullet("Weak unique 1", embedding=weak_embeddings[0], created_by_model="small"),
            make_bullet("Weak unique 2", embedding=weak_embeddings[1], created_by_model="small"),
        ]

        clusterer = BulletClusterer(eps=0.3, min_samples=2)
        strong_result = clusterer.cluster(strong_bullets)

        gaps = clusterer.find_knowledge_gaps(strong_result, weak_bullets)

        # Both weak bullets should be gaps (different topic)
        assert len(gaps) == 2


class TestBuildDistillationPlaybook:
    """Test the main entry point function."""

    def test_builds_diverse_distillation_set(self):
        """Should produce one representative per cluster."""
        # Two distinct topics with different seeds for different embeddings
        auth_base = [1.0] + [0.0] * 383
        test_base = [0.0] * 192 + [1.0] + [0.0] * 191

        auth_embeddings = make_similar_embeddings(auth_base, 3, noise=0.02, seed=100)
        test_embeddings = make_similar_embeddings(test_base, 3, noise=0.02, seed=200)

        bullets = [
            make_bullet("Auth 1", embedding=auth_embeddings[0], helpful_count=5),
            make_bullet("Auth 2", embedding=auth_embeddings[1], helpful_count=10),
            make_bullet("Auth 3", embedding=auth_embeddings[2], helpful_count=3),
            make_bullet("Test 1", embedding=test_embeddings[0], helpful_count=8),
            make_bullet("Test 2", embedding=test_embeddings[1], helpful_count=2),
            make_bullet("Test 3", embedding=test_embeddings[2], helpful_count=6),
        ]

        distillation_set, result = build_distillation_playbook(
            bullets=bullets,
            eps=0.3,
            min_samples=2,
        )

        # Should have 2 representatives (one per cluster)
        assert len(distillation_set) == 2

        # Representatives should be the highest-helpful from each cluster
        # Get the helpful counts of selected bullets
        helpful_counts = sorted([b.helpful_count for b in distillation_set])
        # Auth 2 (10) and Test 1 (8) should be selected as they have highest counts
        assert helpful_counts == [8, 10]


class TestBulletCluster:
    """Test BulletCluster dataclass properties."""

    def test_models_represented(self):
        """Should track unique models in cluster."""
        bullets = [
            make_bullet("A", created_by_model="gpt-4"),
            make_bullet("B", created_by_model="claude"),
            make_bullet("C", created_by_model="gpt-4"),  # Duplicate model
        ]

        cluster = BulletCluster(cluster_id=0, bullets=bullets)

        assert cluster.models_represented == {"gpt-4", "claude"}

    def test_avg_helpful_ratio(self):
        """Should calculate average helpful ratio."""
        bullets = [
            make_bullet("A", helpful_count=8, harmful_count=2),  # 0.8
            make_bullet("B", helpful_count=6, harmful_count=4),  # 0.6
        ]

        cluster = BulletCluster(cluster_id=0, bullets=bullets)

        assert cluster.avg_helpful_ratio == pytest.approx(0.7, rel=0.01)


class TestClusteringResult:
    """Test ClusteringResult dataclass properties."""

    def test_coverage_by_model(self):
        """Should track which models contributed to which clusters."""
        cluster1 = BulletCluster(
            cluster_id=0,
            bullets=[
                make_bullet("A", created_by_model="gpt-4"),
                make_bullet("B", created_by_model="claude"),
            ],
        )
        cluster2 = BulletCluster(
            cluster_id=1,
            bullets=[
                make_bullet("C", created_by_model="gpt-4"),
            ],
        )

        result = ClusteringResult(
            clusters=[cluster1, cluster2],
            outliers=[],
            n_clusters=2,
            n_outliers=0,
            eps=0.3,
            min_samples=2,
        )

        coverage = result.coverage_by_model
        assert coverage["gpt-4"] == 2  # In both clusters
        assert coverage["claude"] == 1  # In one cluster
