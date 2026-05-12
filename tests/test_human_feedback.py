"""Tests for human feedback loop integration (ace_enterprise-e98)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.broker.feedback import (
    RECENCY_HALF_LIFE_DAYS,
    ROLE_WEIGHTS,
    FeedbackCollector,
    HumanFeedback,
)
from src.broker.performance_aggregator import AgentPerformanceMetrics, PerformanceAggregator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collector() -> FeedbackCollector:
    return FeedbackCollector()


def _metrics(agent_ref="m", total=20, successful=16) -> AgentPerformanceMetrics:
    m = AgentPerformanceMetrics(agent_ref=agent_ref)
    m.total_tasks = total
    m.successful_tasks = successful
    m.failed_tasks = total - successful
    return m


def _agg_with(metrics_map: dict[str, AgentPerformanceMetrics]) -> PerformanceAggregator:
    store = MagicMock()
    store.query.return_value = MagicMock(events=[])
    agg = PerformanceAggregator(store)
    agg._cache = metrics_map
    agg._cache_expiry = datetime.now() + timedelta(minutes=5)
    return agg


NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# HumanFeedback dataclass
# ---------------------------------------------------------------------------

class TestHumanFeedbackDataclass:
    def test_fields_accessible(self):
        fb = HumanFeedback(
            evaluation_id="e1", rating=4,
            provider_id="u1", provider_role="developer",
        )
        assert fb.evaluation_id == "e1"
        assert fb.rating == 4
        assert fb.provider_id == "u1"
        assert fb.provider_role == "developer"
        assert fb.comment is None

    def test_comment_optional(self):
        fb = HumanFeedback(
            evaluation_id="e1", rating=3, provider_id="u1",
            provider_role="reviewer", comment="good effort",
        )
        assert fb.comment == "good effort"

    def test_timestamp_defaults_to_now(self):
        before = datetime.now(UTC)
        fb = HumanFeedback(
            evaluation_id="e1", rating=5, provider_id="u1", provider_role="expert",
        )
        after = datetime.now(UTC)
        assert before <= fb.timestamp <= after


# ---------------------------------------------------------------------------
# FeedbackCollector.submit
# ---------------------------------------------------------------------------

class TestFeedbackCollectorSubmit:
    def test_submit_returns_human_feedback(self):
        c = _collector()
        fb = c.submit("e1", 4, "u1", "developer")
        assert isinstance(fb, HumanFeedback)

    def test_submit_stores_feedback(self):
        c = _collector()
        c.submit("e1", 4, "u1", "developer")
        assert c.has_feedback("e1")

    def test_rating_below_one_raises(self):
        c = _collector()
        with pytest.raises(ValueError, match="1-5"):
            c.submit("e1", 0, "u1", "developer")

    def test_rating_above_five_raises(self):
        c = _collector()
        with pytest.raises(ValueError, match="1-5"):
            c.submit("e1", 6, "u1", "developer")

    def test_rating_one_accepted(self):
        c = _collector()
        fb = c.submit("e1", 1, "u1", "developer")
        assert fb.rating == 1

    def test_rating_five_accepted(self):
        c = _collector()
        fb = c.submit("e1", 5, "u1", "developer")
        assert fb.rating == 5

    def test_multiple_feedbacks_for_same_evaluation(self):
        c = _collector()
        c.submit("e1", 4, "u1", "developer")
        c.submit("e1", 3, "u2", "reviewer")
        assert len(c.get_feedback("e1")) == 2

    def test_feedbacks_for_different_evaluations_separate(self):
        c = _collector()
        c.submit("e1", 4, "u1", "developer")
        c.submit("e2", 2, "u2", "reviewer")
        assert len(c.get_feedback("e1")) == 1
        assert len(c.get_feedback("e2")) == 1

    def test_custom_timestamp_stored(self):
        c = _collector()
        ts = datetime(2025, 6, 1, tzinfo=UTC)
        fb = c.submit("e1", 3, "u1", "developer", timestamp=ts)
        assert fb.timestamp == ts


# ---------------------------------------------------------------------------
# FeedbackCollector.get_feedback / get_all_feedback / has_feedback
# ---------------------------------------------------------------------------

class TestFeedbackRetrieval:
    def test_get_feedback_empty_returns_empty_list(self):
        c = _collector()
        assert c.get_feedback("unknown") == []

    def test_has_feedback_false_when_none(self):
        assert not _collector().has_feedback("x")

    def test_has_feedback_true_after_submit(self):
        c = _collector()
        c.submit("e1", 3, "u1", "developer")
        assert c.has_feedback("e1")

    def test_get_all_feedback_aggregates_all(self):
        c = _collector()
        c.submit("e1", 3, "u1", "developer")
        c.submit("e2", 5, "u2", "reviewer")
        assert len(c.get_all_feedback()) == 2

    def test_get_all_feedback_empty_when_none(self):
        assert _collector().get_all_feedback() == []


# ---------------------------------------------------------------------------
# FeedbackCollector.aggregated_rating
# ---------------------------------------------------------------------------

class TestAggregatedRating:
    def test_none_when_no_feedback(self):
        assert _collector().aggregated_rating("e1") is None

    def test_single_rating_returned(self):
        c = _collector()
        c.submit("e1", 4, "u1", "developer")
        assert c.aggregated_rating("e1") == pytest.approx(4.0)

    def test_average_of_multiple_ratings(self):
        c = _collector()
        c.submit("e1", 4, "u1", "developer")
        c.submit("e1", 2, "u2", "reviewer")
        assert c.aggregated_rating("e1") == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# FeedbackCollector.blended_score
# ---------------------------------------------------------------------------

class TestBlendedScore:
    def test_no_feedback_returns_automated_score(self):
        c = _collector()
        assert c.blended_score(70.0, "e1", now=NOW) == pytest.approx(70.0)

    def test_perfect_human_score_pulls_blended_up(self):
        c = _collector()
        c.submit("e1", 5, "u1", "developer", timestamp=NOW)  # maps to 100
        blended = c.blended_score(50.0, "e1", now=NOW)
        assert blended > 50.0

    def test_low_human_score_pulls_blended_down(self):
        c = _collector()
        c.submit("e1", 1, "u1", "developer", timestamp=NOW)  # maps to 0
        blended = c.blended_score(80.0, "e1", now=NOW)
        assert blended < 80.0

    def test_blended_score_clamped_to_100(self):
        c = _collector()
        for _ in range(20):  # many feedbacks → high weight
            c.submit("e1", 5, "u1", "developer", timestamp=NOW)
        assert c.blended_score(100.0, "e1", now=NOW) <= 100.0

    def test_blended_score_clamped_to_zero(self):
        c = _collector()
        for _ in range(20):
            c.submit("e1", 1, "u1", "developer", timestamp=NOW)
        assert c.blended_score(0.0, "e1", now=NOW) >= 0.0

    def test_reviewer_weight_exceeds_developer(self):
        c = _collector()
        assert ROLE_WEIGHTS["reviewer"] > ROLE_WEIGHTS["developer"]

    def test_feedback_weight_increases_with_more_samples(self):
        c1 = _collector()
        c1.submit("e1", 5, "u1", "developer", timestamp=NOW)
        b1 = c1.blended_score(0.0, "e1", now=NOW)

        c2 = _collector()
        for i in range(10):
            c2.submit("e1", 5, f"u{i}", "developer", timestamp=NOW)
        b2 = c2.blended_score(0.0, "e1", now=NOW)

        assert b2 > b1

    def test_stale_feedback_has_less_influence_than_fresh(self):
        now = NOW
        old_ts = now - timedelta(days=RECENCY_HALF_LIFE_DAYS * 4)  # heavily decayed

        c_fresh = _collector()
        c_fresh.submit("e1", 5, "u1", "developer", timestamp=now)
        b_fresh = c_fresh.blended_score(0.0, "e1", now=now)

        c_stale = _collector()
        c_stale.submit("e1", 5, "u1", "developer", timestamp=old_ts)
        b_stale = c_stale.blended_score(0.0, "e1", now=now)

        assert b_fresh > b_stale


# ---------------------------------------------------------------------------
# FeedbackCollector.detect_drift
# ---------------------------------------------------------------------------

class TestDetectDrift:
    def test_no_feedback_returns_zero(self):
        c = _collector()
        assert c.detect_drift(70.0, "e1", now=NOW) == pytest.approx(0.0)

    def test_positive_drift_when_humans_rate_higher(self):
        c = _collector()
        c.submit("e1", 5, "u1", "developer", timestamp=NOW)  # 100 human score
        drift = c.detect_drift(50.0, "e1", now=NOW)
        assert drift > 0.0

    def test_negative_drift_when_humans_rate_lower(self):
        c = _collector()
        c.submit("e1", 1, "u1", "developer", timestamp=NOW)  # 0 human score
        drift = c.detect_drift(80.0, "e1", now=NOW)
        assert drift < 0.0

    def test_zero_drift_when_perfect_agreement(self):
        c = _collector()
        # rating 3 → (3-1)/4*100 = 50
        c.submit("e1", 3, "u1", "developer", timestamp=NOW)
        drift = c.detect_drift(50.0, "e1", now=NOW)
        assert drift == pytest.approx(0.0)

    def test_drift_report_includes_only_evaluated_ids(self):
        c = _collector()
        c.submit("e1", 5, "u1", "developer", timestamp=NOW)
        report = c.drift_report({"e1": 50.0, "e2": 70.0}, now=NOW)
        assert "e1" in report
        assert "e2" not in report  # no feedback for e2

    def test_drift_report_values_are_floats(self):
        c = _collector()
        c.submit("e1", 4, "u1", "developer", timestamp=NOW)
        report = c.drift_report({"e1": 60.0}, now=NOW)
        assert isinstance(report["e1"], float)


# ---------------------------------------------------------------------------
# PerformanceAggregator.get_feedback_adjusted_score
# ---------------------------------------------------------------------------

class TestFeedbackAdjustedScore:
    def test_no_feedback_returns_reliability_score_times_100(self):
        m = _metrics(total=20, successful=20)
        agg = _agg_with({"m": m})
        c = _collector()
        score = agg.get_feedback_adjusted_score("m", ["e1"], c)
        assert score == pytest.approx(m.reliability_score * 100.0)

    def test_positive_feedback_raises_score(self):
        m = _metrics(total=20, successful=10)  # 50% → 50 automated
        agg = _agg_with({"m": m})
        c = _collector()
        c.submit("e1", 5, "u1", "developer", timestamp=NOW)  # excellent rating
        score = agg.get_feedback_adjusted_score("m", ["e1"], c)
        assert score > m.reliability_score * 100.0

    def test_negative_feedback_lowers_score(self):
        m = _metrics(total=20, successful=20)  # 100% → 100 automated
        agg = _agg_with({"m": m})
        c = _collector()
        c.submit("e1", 1, "u1", "developer", timestamp=NOW)  # terrible rating
        score = agg.get_feedback_adjusted_score("m", ["e1"], c)
        assert score < m.reliability_score * 100.0

    def test_empty_evaluation_ids_returns_automated_score(self):
        m = _metrics(total=20, successful=16)
        agg = _agg_with({"m": m})
        c = _collector()
        score = agg.get_feedback_adjusted_score("m", [], c)
        assert score == pytest.approx(m.reliability_score * 100.0)

    def test_averages_blended_scores_across_evaluations(self):
        m = _metrics(total=20, successful=10)
        agg = _agg_with({"m": m})
        c = _collector()
        c.submit("e1", 5, "u1", "developer", timestamp=NOW)
        c.submit("e2", 1, "u1", "developer", timestamp=NOW)
        score1 = agg.get_feedback_adjusted_score("m", ["e1"], c)
        score2 = agg.get_feedback_adjusted_score("m", ["e2"], c)
        score_both = agg.get_feedback_adjusted_score("m", ["e1", "e2"], c)
        assert score_both == pytest.approx((score1 + score2) / 2, abs=1e-6)
