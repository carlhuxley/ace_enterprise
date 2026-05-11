"""Tests for ConsensusBuilder (ace_enterprise-4ee).

Methods that call the embedding service (cluster_bullets, build_consensus,
calculate_diversity_score, get_unique_contributions) are tested with a
deterministic mock embedder: identical text → same unit vector (similarity 1.0),
distinct text → orthogonal vectors (similarity 0.0). Pure methods
(_cosine_similarity, _merge_cluster, calculate_consensus_strength,
get_agreement_matrix) are tested directly without mocking.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.ensemble.models import BulletSection, ConsensusBullet, Vote, VoteType


# ---------------------------------------------------------------------------
# Deterministic embedding mock
# ---------------------------------------------------------------------------

def _make_embed_mock():
    """Return a mock embedding service.

    Each unique text string gets a distinct basis vector; identical strings get
    the same vector. Cosine similarity between distinct basis vectors is 0.0;
    between identical ones it is 1.0.
    """
    seen: dict[str, list[float]] = {}

    def embed_batch(texts):
        # Ensure the vector space is large enough for all unique texts
        dim = max(len(texts), len(seen) + len(set(texts) - set(seen.keys())) + 1)
        for text in texts:
            if text not in seen:
                idx = len(seen)
                vec = [1.0 if j == idx else 0.0 for j in range(dim)]
                seen[text] = vec
            else:
                # Pad existing vector to current dim
                if len(seen[text]) < dim:
                    seen[text] = seen[text] + [0.0] * (dim - len(seen[text]))
        return [seen[t] for t in texts]

    service = MagicMock()
    service.embed_batch.side_effect = embed_batch
    return service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bullet(content="validate inputs", proposer="model-a", tags=None):
    return ConsensusBullet(
        content=content,
        section=BulletSection.STRATEGIES,
        proposed_by=proposer,
        proposal_reasoning="test",
        tags=tags or [],
    )


def _vote(model_id, vote_type, confidence=0.8):
    return Vote(model_id=model_id, vote=vote_type, reasoning="test", confidence=confidence)


def _builder(threshold=0.85):
    with patch("src.ensemble.consensus.get_embedding_service", return_value=_make_embed_mock()):
        from src.ensemble.consensus import ConsensusBuilder
        return ConsensusBuilder(similarity_threshold=threshold)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConsensusBuilderInit:
    def test_stores_similarity_threshold(self):
        cb = _builder(threshold=0.9)
        assert cb.similarity_threshold == 0.9

    def test_default_threshold(self):
        cb = _builder()
        assert cb.similarity_threshold == 0.85

    def test_embedding_service_initialised(self):
        cb = _builder()
        assert cb.embedding_service is not None


# ---------------------------------------------------------------------------
# _cosine_similarity — pure math
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def setup_method(self):
        self.cb = _builder()

    def test_identical_vectors_return_one(self):
        v = [1.0, 0.0, 0.0]
        assert self.cb._cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_return_zero(self):
        assert self.cb._cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_zero_vector_returns_zero(self):
        assert self.cb._cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_both_zero_vectors_return_zero(self):
        assert self.cb._cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0

    def test_partial_overlap(self):
        result = self.cb._cosine_similarity([1.0, 1.0], [1.0, 0.0])
        assert 0.0 < result < 1.0


# ---------------------------------------------------------------------------
# _merge_cluster — pure logic
# ---------------------------------------------------------------------------

class TestMergeCluster:
    def setup_method(self):
        self.cb = _builder()

    def test_picks_longest_content_as_base(self):
        b1 = _bullet("short", "m1")
        b2 = _bullet("a much longer bullet content here", "m2")
        merged = self.cb._merge_cluster([b1, b2])
        assert merged.content == b2.content

    def test_proposed_by_reflects_count(self):
        bullets = [_bullet("x", f"model-{i}") for i in range(3)]
        merged = self.cb._merge_cluster(bullets)
        assert merged.proposed_by == "consensus_3"

    def test_tags_combined(self):
        b1 = _bullet("x", "m1", tags=["alpha"])
        b2 = _bullet("xy longer", "m2", tags=["beta"])
        merged = self.cb._merge_cluster([b1, b2])
        assert "alpha" in merged.tags
        assert "beta" in merged.tags

    def test_reasoning_mentions_merge(self):
        bullets = [_bullet("a", "m1"), _bullet("ab longer", "m2")]
        merged = self.cb._merge_cluster(bullets)
        assert "Merged" in merged.proposal_reasoning

    def test_section_preserved_from_base(self):
        b1 = _bullet("short text", "m1")
        b2 = _bullet("longer text here", "m2")
        merged = self.cb._merge_cluster([b1, b2])
        assert merged.section == BulletSection.STRATEGIES

    def test_similar_bullets_tracked(self):
        b1 = _bullet("short", "m1")
        b2 = _bullet("longer version of same idea", "m2")
        merged = self.cb._merge_cluster([b1, b2])
        assert len(merged.similar_bullets) == 1


# ---------------------------------------------------------------------------
# cluster_bullets
# ---------------------------------------------------------------------------

class TestClusterBullets:
    def test_empty_returns_empty_dict(self):
        cb = _builder()
        assert cb.cluster_bullets([]) == {}

    def test_single_bullet_forms_one_cluster(self):
        cb = _builder()
        b = _bullet("unique text A")
        clusters = cb.cluster_bullets([b])
        assert len(clusters) == 1

    def test_identical_content_bullets_cluster_together(self):
        cb = _builder(threshold=0.85)
        same = "identical content"
        b1 = _bullet(same, "m1")
        b2 = _bullet(same, "m2")
        clusters = cb.cluster_bullets([b1, b2])
        # Both have similarity 1.0 → should be in one cluster
        assert len(clusters) == 1

    def test_distinct_content_bullets_form_separate_clusters(self):
        cb = _builder(threshold=0.85)
        b1 = _bullet("alpha unique", "m1")
        b2 = _bullet("beta unique", "m2")
        clusters = cb.cluster_bullets([b1, b2])
        # Orthogonal embeddings → similarity 0.0 < 0.85 → separate clusters
        assert len(clusters) == 2

    def test_cluster_id_assigned_to_bullets(self):
        cb = _builder()
        b = _bullet("something")
        cb.cluster_bullets([b])
        assert b.cluster_id is not None

    def test_similar_bullets_share_cluster_id(self):
        cb = _builder(threshold=0.85)
        same = "shared text"
        b1 = _bullet(same, "m1")
        b2 = _bullet(same, "m2")
        cb.cluster_bullets([b1, b2])
        assert b1.cluster_id == b2.cluster_id


# ---------------------------------------------------------------------------
# build_consensus
# ---------------------------------------------------------------------------

class TestBuildConsensus:
    def test_empty_returns_empty_list(self):
        cb = _builder()
        assert cb.build_consensus([]) == []

    def test_single_bullet_preserved(self):
        cb = _builder()
        b = _bullet("unique alpha")
        result = cb.build_consensus([b])
        assert len(result) == 1
        assert result[0].content == b.content

    def test_identical_bullets_merged_to_one(self):
        cb = _builder(threshold=0.85)
        same = "same content here"
        b1 = _bullet(same, "m1")
        b2 = _bullet(same, "m2")
        result = cb.build_consensus([b1, b2])
        assert len(result) == 1

    def test_distinct_bullets_all_kept(self):
        cb = _builder(threshold=0.85)
        b1 = _bullet("alpha distinct", "m1")
        b2 = _bullet("beta distinct", "m2")
        b3 = _bullet("gamma distinct", "m3")
        result = cb.build_consensus([b1, b2, b3])
        assert len(result) == 3

    def test_merged_bullet_has_consensus_proposer(self):
        cb = _builder(threshold=0.85)
        same = "shared idea"
        b1 = _bullet(same, "m1")
        b2 = _bullet(same, "m2")
        result = cb.build_consensus([b1, b2])
        assert result[0].proposed_by.startswith("consensus_")


# ---------------------------------------------------------------------------
# calculate_diversity_score
# ---------------------------------------------------------------------------

class TestCalculateDiversityScore:
    def test_empty_returns_zero(self):
        cb = _builder()
        assert cb.calculate_diversity_score([]) == 0.0

    def test_all_unique_returns_one(self):
        cb = _builder(threshold=0.85)
        bullets = [_bullet(f"unique content {i}") for i in range(3)]
        score = cb.calculate_diversity_score(bullets)
        assert score == pytest.approx(1.0)

    def test_all_identical_returns_fraction(self):
        cb = _builder(threshold=0.85)
        same = "repeated bullet"
        bullets = [_bullet(same, f"m{i}") for i in range(4)]
        score = cb.calculate_diversity_score(bullets)
        # 1 cluster / 4 bullets = 0.25
        assert score == pytest.approx(0.25)

    def test_score_between_zero_and_one(self):
        cb = _builder(threshold=0.85)
        bullets = [_bullet("content a"), _bullet("content a"), _bullet("content b")]
        score = cb.calculate_diversity_score(bullets)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# calculate_consensus_strength — pure computation on votes
# ---------------------------------------------------------------------------

class TestCalculateConsensusStrength:
    def setup_method(self):
        self.cb = _builder()

    def test_empty_returns_zero(self):
        assert self.cb.calculate_consensus_strength([]) == 0.0

    def test_no_votes_returns_zero(self):
        b = _bullet()  # no votes
        assert self.cb.calculate_consensus_strength([b]) == 0.0

    def test_unanimous_approval_returns_high_score(self):
        b = _bullet()
        b.votes = [_vote("m1", VoteType.APPROVE), _vote("m2", VoteType.APPROVE)]
        score = self.cb.calculate_consensus_strength([b])
        assert score > 0.5

    def test_split_votes_returns_lower_than_unanimous(self):
        unanimous = _bullet("u")
        unanimous.votes = [_vote("m1", VoteType.APPROVE), _vote("m2", VoteType.APPROVE)]

        split = _bullet("s")
        split.votes = [_vote("m1", VoteType.APPROVE), _vote("m2", VoteType.REJECT)]

        score_unanimous = self.cb.calculate_consensus_strength([unanimous])
        score_split = self.cb.calculate_consensus_strength([split])
        assert score_unanimous > score_split

    def test_all_rejection_returns_zero(self):
        b = _bullet()
        b.votes = [_vote("m1", VoteType.REJECT), _vote("m2", VoteType.REJECT)]
        score = self.cb.calculate_consensus_strength([b])
        assert score == pytest.approx(0.0)

    def test_score_between_zero_and_one(self):
        b = _bullet()
        b.votes = [_vote("m1", VoteType.APPROVE), _vote("m2", VoteType.REJECT)]
        score = self.cb.calculate_consensus_strength([b])
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# get_unique_contributions
# ---------------------------------------------------------------------------

class TestGetUniqueContributions:
    def test_single_bullet_is_unique_to_proposer(self):
        cb = _builder()
        b = _bullet("alpha unique proposal", "model-x")
        result = cb.get_unique_contributions([b])
        assert "model-x" in result
        assert len(result["model-x"]) == 1

    def test_duplicate_bullets_not_counted_as_unique(self):
        cb = _builder(threshold=0.85)
        same = "shared idea text"
        b1 = _bullet(same, "m1")
        b2 = _bullet(same, "m2")
        result = cb.get_unique_contributions([b1, b2])
        # Both in same cluster → neither is unique
        assert "m1" not in result
        assert "m2" not in result

    def test_distinct_bullets_each_unique(self):
        cb = _builder(threshold=0.85)
        b1 = _bullet("alpha idea", "m1")
        b2 = _bullet("beta idea", "m2")
        result = cb.get_unique_contributions([b1, b2])
        assert "m1" in result
        assert "m2" in result

    def test_empty_returns_empty(self):
        cb = _builder()
        assert cb.get_unique_contributions([]) == {}


# ---------------------------------------------------------------------------
# get_agreement_matrix — pure iteration on votes
# ---------------------------------------------------------------------------

class TestGetAgreementMatrix:
    def setup_method(self):
        self.cb = _builder()

    def test_empty_returns_empty(self):
        assert self.cb.get_agreement_matrix([]) == {}

    def test_two_models_agree_returns_one(self):
        b = _bullet()
        b.votes = [
            _vote("m1", VoteType.APPROVE),
            _vote("m2", VoteType.APPROVE),
        ]
        matrix = self.cb.get_agreement_matrix([b])
        assert matrix[("m1", "m2")] == pytest.approx(1.0)

    def test_two_models_disagree_returns_zero(self):
        b = _bullet()
        b.votes = [
            _vote("m1", VoteType.APPROVE),
            _vote("m2", VoteType.REJECT),
        ]
        matrix = self.cb.get_agreement_matrix([b])
        assert matrix[("m1", "m2")] == pytest.approx(0.0)

    def test_partial_agreement_across_bullets(self):
        b1 = _bullet("x")
        b1.votes = [_vote("m1", VoteType.APPROVE), _vote("m2", VoteType.APPROVE)]
        b2 = _bullet("y")
        b2.votes = [_vote("m1", VoteType.APPROVE), _vote("m2", VoteType.REJECT)]
        matrix = self.cb.get_agreement_matrix([b1, b2])
        # 1 agree out of 2 → 0.5
        assert matrix[("m1", "m2")] == pytest.approx(0.5)

    def test_pair_only_when_both_voted(self):
        b = _bullet()
        b.votes = [_vote("m1", VoteType.APPROVE)]  # only m1 voted
        matrix = self.cb.get_agreement_matrix([b])
        # No pair (m1, m2) since m2 never voted
        assert ("m1", "m2") not in matrix

    def test_matrix_keys_are_sorted_pairs(self):
        b = _bullet()
        b.votes = [_vote("z-model", VoteType.APPROVE), _vote("a-model", VoteType.APPROVE)]
        matrix = self.cb.get_agreement_matrix([b])
        # Sorted: ("a-model", "z-model")
        assert ("a-model", "z-model") in matrix
        assert ("z-model", "a-model") not in matrix
