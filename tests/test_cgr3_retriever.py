"""Tests for ContextGraphRetriever (src/retrieval/cgr3_retriever.py) -- the
REASON phase and overall RETRIEVE->RANK->REASON pipeline orchestration.
Previously had zero test coverage anywhere (see test_cgr3_confidence_forwarding.py
for the specific min_confidence-forwarding regression found and fixed earlier;
this file covers the rest of the pipeline).
"""
from datetime import UTC, datetime

from src.retrieval.cgr3_retriever import ContextGraphRetriever
from src.retrieval.schemas import ContextGap, ReasoningVerdict, RetrievalContext
from src.storage.schemas import Bullet

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _bullet(id="ctx-1", content="always validate input", **kw):
    defaults = dict(id=id, content=content, section="strategies_and_hard_rules", created_at=_NOW)
    defaults.update(kw)
    return Bullet(**defaults)


class _StubBaseRetriever:
    """Returns exactly the (bullet, score) pairs it's given, ignoring the
    query -- isolates ContextGraphRetriever's own RANK/REASON logic from
    BulletRetriever's RETRIEVE scoring (covered separately)."""

    def __init__(self, candidates):
        self._candidates = candidates
        self.calls = []

    def retrieve(self, **kwargs):
        self.calls.append(kwargs)
        return self._candidates


class _StubContextScorer:
    """Returns a fixed (score, gaps) pair regardless of bullet/context."""

    def __init__(self, score, gaps=None):
        self._score = score
        self._gaps = gaps or []

    def score(self, bullet, context):
        return self._score, self._gaps


def _retriever(candidates, context_score, gaps=None, **kwargs):
    return ContextGraphRetriever(
        base_retriever=_StubBaseRetriever(candidates),
        context_scorer=_StubContextScorer(context_score, gaps),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# _determine_verdict thresholds
# ---------------------------------------------------------------------------

class TestVerdictThresholds:
    def test_below_skip_threshold_is_skip(self):
        cgr = _retriever([(_bullet(), 0.9)], context_score=0.10)  # < skip_threshold=0.15
        response = cgr.retrieve("q", [_bullet()])
        assert response.apply == [] and response.ask_first == []

    def test_between_skip_and_min_context_is_ask_first(self):
        cgr = _retriever([(_bullet(), 0.9)], context_score=0.20)  # 0.15 <= x < 0.3
        response = cgr.retrieve("q", [_bullet()])
        assert len(response.ask_first) == 1
        assert response.ask_first[0].verdict == ReasoningVerdict.ASK_FIRST

    def test_sufficient_context_no_gaps_is_apply(self):
        cgr = _retriever([(_bullet(), 0.9)], context_score=0.9, gaps=[])
        response = cgr.retrieve("q", [_bullet()])
        assert len(response.apply) == 1
        assert response.apply[0].verdict == ReasoningVerdict.APPLY

    def test_sufficient_context_but_too_many_gaps_is_skip(self):
        gaps = [ContextGap(dimension="d", description="x", severity=0.9) for _ in range(3)]
        cgr = _retriever([(_bullet(), 0.9)], context_score=0.9, gaps=gaps, max_gaps_for_ask=2)
        response = cgr.retrieve("q", [_bullet()])
        assert response.apply == [] and response.ask_first == []

    def test_sufficient_context_with_some_gaps_is_ask_first(self):
        gaps = [ContextGap(dimension="d", description="x", severity=0.9)]
        cgr = _retriever(
            [(_bullet(), 0.9)], context_score=0.9, gaps=gaps,
            max_gaps_for_apply=0, max_gaps_for_ask=2,
        )
        response = cgr.retrieve("q", [_bullet()])
        assert len(response.ask_first) == 1

    def test_gaps_below_severity_threshold_dont_count(self):
        # severity <= 0.3 is not "significant" -- shouldn't push APPLY to ASK_FIRST
        gaps = [ContextGap(dimension="d", description="minor", severity=0.2)]
        cgr = _retriever([(_bullet(), 0.9)], context_score=0.9, gaps=gaps, max_gaps_for_apply=0)
        response = cgr.retrieve("q", [_bullet()])
        assert len(response.apply) == 1

    def test_custom_thresholds_are_respected(self):
        cgr = _retriever(
            [(_bullet(), 0.9)], context_score=0.5,
            skip_threshold=0.6,  # 0.5 < 0.6 -> SKIP even though it'd normally ASK_FIRST
        )
        response = cgr.retrieve("q", [_bullet()])
        assert response.apply == [] and response.ask_first == []


# ---------------------------------------------------------------------------
# Pipeline behavior: empty results, sorting, top_k, categorization
# ---------------------------------------------------------------------------

class TestRetrievePipeline:
    def test_no_candidates_returns_empty_response_fast(self):
        cgr = _retriever([], context_score=0.9)
        response = cgr.retrieve("q", [])
        assert response.total_candidates == 0
        assert response.apply == [] and response.ask_first == []

    def test_default_context_used_when_none_given(self):
        cgr = _retriever([(_bullet(), 0.9)], context_score=0.9)
        response = cgr.retrieve("q", [_bullet()], context=None)
        assert isinstance(response.context, RetrievalContext)

    def test_sorted_by_combined_score_descending(self):
        weak, strong = _bullet(id="weak"), _bullet(id="strong")
        # Use a real (non-stub) scorer isn't needed -- vary semantic_score,
        # keep context_score fixed via the stub.
        cgr = _retriever([(weak, 0.1), (strong, 0.9)], context_score=0.9)
        response = cgr.retrieve("q", [weak, strong])
        assert [rb.bullet.id for rb in response.apply] == ["strong", "weak"]

    def test_top_k_truncates_after_sorting(self):
        bullets = [_bullet(id=f"b{i}") for i in range(5)]
        candidates = [(b, 1.0 - i * 0.1) for i, b in enumerate(bullets)]
        cgr = _retriever(candidates, context_score=0.9)
        response = cgr.retrieve("q", bullets, top_k=2)
        assert len(response.apply) == 2
        assert [rb.bullet.id for rb in response.apply] == ["b0", "b1"]

    def test_combined_score_blends_semantic_and_context_by_weight(self):
        cgr = _retriever(
            [(_bullet(), 0.0)], context_score=1.0, context_weight=0.4,
        )
        response = cgr.retrieve("q", [_bullet()])
        rb = response.apply[0]
        assert rb.combined_score == 0.0 * 0.6 + 1.0 * 0.4

    def test_total_candidates_reflects_pre_topk_count(self):
        bullets = [_bullet(id=f"b{i}") for i in range(5)]
        candidates = [(b, 0.9) for b in bullets]
        cgr = _retriever(candidates, context_score=0.9)
        response = cgr.retrieve("q", bullets, top_k=2)
        assert response.total_candidates == 5

    def test_min_confidence_is_forwarded_to_base_retriever(self):
        stub = _StubBaseRetriever([(_bullet(), 0.9)])
        cgr = ContextGraphRetriever(base_retriever=stub, context_scorer=_StubContextScorer(0.9))
        cgr.retrieve("q", [_bullet()], min_confidence=0.0)
        assert stub.calls[0]["min_confidence"] == 0.0


# ---------------------------------------------------------------------------
# explain_verdict
# ---------------------------------------------------------------------------

class TestExplainVerdict:
    def test_includes_scores_and_verdict(self):
        cgr = _retriever([(_bullet(content="use pathlib for paths"), 0.9)], context_score=0.9)
        response = cgr.retrieve("q", [_bullet()])
        explanation = cgr.explain_verdict(response.apply[0])
        assert "APPLY" in explanation
        assert "Semantic score" in explanation
        assert "Context score" in explanation

    def test_includes_context_gaps_when_present(self):
        gaps = [ContextGap(dimension="team", description="wrong team", severity=0.9)]
        cgr = _retriever(
            [(_bullet(), 0.9)], context_score=0.9, gaps=gaps,
            max_gaps_for_apply=0, max_gaps_for_ask=2,
        )
        response = cgr.retrieve("q", [_bullet()])
        explanation = cgr.explain_verdict(response.ask_first[0])
        assert "wrong team" in explanation
        assert "[team]" in explanation


# ---------------------------------------------------------------------------
# retrieve_with_lineage -- documented as lineage-aware filtering, but is
# actually just a TODO stub delegating straight to retrieve().
# ---------------------------------------------------------------------------

class TestRetrieveWithLineageIsAStub:
    def test_delegates_to_plain_retrieve_without_lineage_filtering(self):
        """No BulletLineageModel filtering happens despite the docstring --
        include_superseded is accepted but has no effect either way."""
        cgr = _retriever([(_bullet(), 0.9)], context_score=0.9)
        excluded = cgr.retrieve_with_lineage("q", [_bullet()], include_superseded=False)
        included = cgr.retrieve_with_lineage("q", [_bullet()], include_superseded=True)
        assert len(excluded.apply) == len(included.apply) == 1
