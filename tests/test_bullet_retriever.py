"""Tests for BulletRetriever (src/playbook/retrieval.py) -- the RETRIEVE
phase of CGR3. Previously had zero test coverage anywhere.

No real embedding model needed: bullets without an `embedding` field use the
keyword-only scoring path, which is what most of these tests exercise. A
handful of tests use small synthetic vectors to exercise the semantic path's
pure math (_cosine_similarity) without loading sentence-transformers.
"""
from datetime import UTC, datetime, timedelta

import pytest

from src.playbook.retrieval import BulletRetriever
from src.storage.schemas import Bullet

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _bullet(content="always validate input", section="strategies_and_hard_rules", **kw):
    defaults = dict(
        id=kw.pop("id", "ctx-00001"),
        content=content,
        section=section,
        created_at=_NOW,
    )
    defaults.update(kw)
    return Bullet(**defaults)


# ---------------------------------------------------------------------------
# Keyword-only scoring (no embeddings)
# ---------------------------------------------------------------------------

class TestKeywordOnlyScoring:
    def test_full_keyword_overlap_scores_high(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        b = _bullet(content="always validate database timeout")
        result = retriever.retrieve("database timeout", [b])
        assert len(result) == 1
        assert result[0][1] > 0.5

    def test_no_keyword_overlap_scores_low(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        b = _bullet(content="always validate database timeout")
        result = retriever.retrieve("unrelated banana recipe", [b])
        assert result[0][1] < 0.2

    def test_below_similarity_threshold_is_excluded(self):
        retriever = BulletRetriever(similarity_threshold=0.9)
        b = _bullet(content="database timeout")
        # Only half the query words are covered by content -> keyword_score=0.5,
        # total = 0.5*0.9 + ratio_boost(0.05) = 0.5, well under 0.9.
        result = retriever.retrieve("database unrelated_word", [b])
        assert result == []

    def test_full_coverage_clears_a_nontrivial_threshold(self):
        retriever = BulletRetriever(similarity_threshold=0.5)
        b = _bullet(content="database timeout")
        result = retriever.retrieve("database timeout", [b])
        assert len(result) == 1

    def test_empty_bullets_returns_empty(self):
        retriever = BulletRetriever()
        assert retriever.retrieve("anything", []) == []

    def test_empty_query_scores_near_zero(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        b = _bullet(content="database timeout")
        result = retriever.retrieve("", [b])
        assert result[0][1] < 0.1  # keyword=0, only a small neutral helpful-ratio boost


# ---------------------------------------------------------------------------
# Semantic scoring (synthetic embeddings, no real model needed)
# ---------------------------------------------------------------------------

class TestSemanticScoring:
    def test_identical_embeddings_score_highest(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        b_same = _bullet(id="ctx-1", content="x", embedding=[1.0, 0.0, 0.0])
        b_orth = _bullet(id="ctx-2", content="x", embedding=[0.0, 1.0, 0.0])
        result = retriever.retrieve("query", [b_same, b_orth], query_embedding=[1.0, 0.0, 0.0])
        scores = {b.id: score for b, score in result}
        assert scores["ctx-1"] > scores["ctx-2"]

    def test_missing_bullet_embedding_falls_back_to_keyword_only(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        b = _bullet(content="database timeout", embedding=None)
        # query_embedding given but bullet has none -> semantic_score stays 0,
        # falls into the keyword-only branch (weight 0.9 instead of 0.6)
        result = retriever.retrieve("database timeout", [b], query_embedding=[1.0, 0.0])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Confidence / domain / project / section filters
# ---------------------------------------------------------------------------

class TestFilters:
    def test_confidence_below_min_is_excluded(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        b = _bullet(content="x match", confidence_score=0.2)
        result = retriever.retrieve("x match", [b], min_confidence=0.5)
        assert result == []

    def test_confidence_at_min_is_included(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        b = _bullet(content="x match", confidence_score=0.5)
        result = retriever.retrieve("x match", [b], min_confidence=0.5)
        assert len(result) == 1

    def test_min_confidence_zero_includes_low_confidence_bullet(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        b = _bullet(content="x match", confidence_score=0.3)
        result = retriever.retrieve("x match", [b], min_confidence=0.0)
        assert len(result) == 1

    def test_domain_filter_excludes_mismatched_bullet(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        b = _bullet(content="x match", applicable_domains=["fintech"])
        result = retriever.retrieve("x match", [b], domain="healthcare")
        assert result == []

    def test_domain_filter_includes_bullet_with_no_domain_set(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        b = _bullet(content="x match", applicable_domains=None)
        result = retriever.retrieve("x match", [b], domain="healthcare")
        assert len(result) == 1

    def test_project_filter_excludes_mismatched_bullet(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        b = _bullet(content="x match", project_ids=["proj-a"])
        result = retriever.retrieve("x match", [b], project_id="proj-b")
        assert result == []

    def test_section_filter_excludes_other_sections(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        b = _bullet(content="x match", section="troubleshooting")
        result = retriever.retrieve("x match", [b], filter_section="code_snippets")
        assert result == []

    def test_min_helpful_ratio_excludes_low_ratio_bullet(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        b = _bullet(content="x match", helpful_count=1, harmful_count=9)  # ratio 0.1
        result = retriever.retrieve("x match", [b], min_helpful_ratio=0.5)
        assert result == []

    def test_bullet_with_no_feedback_has_neutral_ratio(self):
        # helpful_count=harmful_count=0 -> ratio 0.5, should pass a 0.5 threshold
        retriever = BulletRetriever(similarity_threshold=0.0)
        b = _bullet(content="x match", helpful_count=0, harmful_count=0)
        result = retriever.retrieve("x match", [b], min_helpful_ratio=0.5)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# top_k
# ---------------------------------------------------------------------------

class TestTopK:
    def test_top_k_limits_results(self):
        retriever = BulletRetriever(top_k=2, similarity_threshold=0.0)
        bullets = [_bullet(id=f"ctx-{i}", content="database timeout") for i in range(5)]
        result = retriever.retrieve("database timeout", bullets)
        assert len(result) == 2

    def test_results_sorted_descending_by_score(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        strong = _bullet(id="ctx-strong", content="database connection timeout retry")
        weak = _bullet(id="ctx-weak", content="database")
        result = retriever.retrieve("database connection timeout retry", [weak, strong])
        assert [b.id for b, _ in result] == ["ctx-strong", "ctx-weak"]


# ---------------------------------------------------------------------------
# retrieve_by_ids
# ---------------------------------------------------------------------------

class TestRetrieveByIds:
    def test_returns_bullets_in_requested_order(self):
        retriever = BulletRetriever()
        b1, b2 = _bullet(id="ctx-1"), _bullet(id="ctx-2")
        result = retriever.retrieve_by_ids(["ctx-2", "ctx-1"], [b1, b2])
        assert [b.id for b in result] == ["ctx-2", "ctx-1"]

    def test_missing_id_is_silently_skipped(self):
        retriever = BulletRetriever()
        b1 = _bullet(id="ctx-1")
        result = retriever.retrieve_by_ids(["ctx-1", "ctx-missing"], [b1])
        assert [b.id for b in result] == ["ctx-1"]


# ---------------------------------------------------------------------------
# filter_by_tags
# ---------------------------------------------------------------------------

class TestFilterByTags:
    def test_required_tags_use_or_logic(self):
        retriever = BulletRetriever()
        a = _bullet(id="a", tags=["python"])
        b = _bullet(id="b", tags=["go"])
        c = _bullet(id="c", tags=["rust"])
        result = retriever.filter_by_tags([a, b, c], required_tags=["python", "go"])
        assert {x.id for x in result} == {"a", "b"}

    def test_excluded_tags_remove_matches(self):
        retriever = BulletRetriever()
        a = _bullet(id="a", tags=["deprecated"])
        b = _bullet(id="b", tags=["current"])
        result = retriever.filter_by_tags([a, b], excluded_tags=["deprecated"])
        assert [x.id for x in result] == ["b"]


# ---------------------------------------------------------------------------
# get_section_distribution
# ---------------------------------------------------------------------------

class TestSectionDistribution:
    def test_counts_per_section(self):
        retriever = BulletRetriever()
        retrieved = [
            (_bullet(id="a", section="troubleshooting"), 0.9),
            (_bullet(id="b", section="troubleshooting"), 0.8),
            (_bullet(id="c", section="code_snippets"), 0.7),
        ]
        dist = retriever.get_section_distribution(retrieved)
        assert dist == {"troubleshooting": 2, "code_snippets": 1}


# ---------------------------------------------------------------------------
# rerank_by_recency
# ---------------------------------------------------------------------------

class TestRerankByRecency:
    def test_more_recent_bullet_can_overtake_slightly_higher_score(self):
        # Note: recency is normalized as created_at.timestamp() / max_timestamp
        # (raw epoch ratio), not relative age -- for bullets this close in
        # absolute time, the "boost" difference is small (a few % at most),
        # so this needs a real age gap + high weight to reliably flip a small
        # initial score gap, not just any (weight, gap) pair.
        retriever = BulletRetriever()
        old = _bullet(id="old", created_at=_NOW - timedelta(days=5 * 365))
        new = _bullet(id="new", created_at=_NOW)
        scored = [(old, 0.50), (new, 0.49)]
        reranked = retriever.rerank_by_recency(scored, recency_weight=1.0)
        assert reranked[0][0].id == "new"

    def test_empty_list_returns_empty(self):
        retriever = BulletRetriever()
        assert retriever.rerank_by_recency([]) == []


# ---------------------------------------------------------------------------
# retrieve_cross_model
# ---------------------------------------------------------------------------

class TestRetrieveCrossModel:
    def test_primary_bullets_score_at_full_weight(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        primary = [_bullet(id="p1", content="database timeout")]
        result = retriever.retrieve_cross_model(
            "database timeout", primary, {}, primary_playbook_id="pb-primary",
        )
        assert result[0][2] == "pb-primary"

    def test_secondary_bullets_are_weighted_down(self):
        retriever = BulletRetriever(similarity_threshold=0.0)
        primary = [_bullet(id="p1", content="database timeout")]
        secondary = {"pb-other": [_bullet(id="s1", content="database timeout")]}
        result = retriever.retrieve_cross_model(
            "database timeout", primary, secondary,
            primary_playbook_id="pb-primary", secondary_weight=0.5,
        )
        scores = {src: score for _, score, src in result}
        assert scores["pb-other"] < scores["pb-primary"]

    def test_secondary_bullets_thresholded_before_weighting(self):
        # A secondary bullet whose raw score clears similarity_threshold but
        # would drop below it after weighting must still be included --
        # the threshold check happens on the raw score.
        retriever = BulletRetriever(similarity_threshold=0.6)
        primary = []
        secondary = {"pb-other": [_bullet(id="s1", content="database timeout retry logic")]}
        result = retriever.retrieve_cross_model(
            "database timeout retry logic", primary, secondary,
            primary_playbook_id="pb-primary", secondary_weight=0.5,
        )
        assert len(result) == 1
        assert result[0][1] < 0.6  # weighted score now below the raw threshold
