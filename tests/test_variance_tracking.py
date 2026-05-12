"""Tests for output consistency/variance tracking (ace_enterprise-mm9)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.benchmark.blind_evaluation import (
    BlindEvaluator,
    EvaluationResult,
    MultiRunResult,
    Submission,
)
from src.broker.adaptive_broker import AdaptiveBroker, BrokerConfig
from src.broker.performance_aggregator import (
    AgentPerformanceMetrics,
    PerformanceAggregator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _submission(task_id="t1", submission_id="s1", content="x = 1"):
    return Submission(
        task_id=task_id,
        submission_id=submission_id,
        output_type="code",
        output_content=content,
    )


def _metrics(
    agent_ref="m",
    total=20,
    successful=16,
    variance_coefficient: float = 0.0,
    consistency_rate: float = 1.0,
) -> AgentPerformanceMetrics:
    m = AgentPerformanceMetrics(agent_ref=agent_ref)
    m.total_tasks = total
    m.successful_tasks = successful
    m.failed_tasks = total - successful
    m.variance_coefficient = variance_coefficient
    m.consistency_rate = consistency_rate
    return m


def _broker(metrics_map: dict[str, AgentPerformanceMetrics]) -> AdaptiveBroker:
    store = MagicMock()
    store.query.return_value = MagicMock(events=[])
    agg = PerformanceAggregator(store)
    agg._cache = metrics_map
    agg._cache_expiry = datetime.now() + timedelta(minutes=5)
    return AdaptiveBroker(agg)


# ---------------------------------------------------------------------------
# AgentPerformanceMetrics new fields
# ---------------------------------------------------------------------------

class TestVarianceFields:
    def test_default_variance_coefficient_is_zero(self):
        m = AgentPerformanceMetrics(agent_ref="m")
        assert m.variance_coefficient == 0.0

    def test_default_consistency_rate_is_one(self):
        m = AgentPerformanceMetrics(agent_ref="m")
        assert m.consistency_rate == 1.0

    def test_variance_adjusted_reliability_equals_reliability_at_defaults(self):
        m = _metrics(total=20, successful=16)
        assert m.variance_adjusted_reliability == pytest.approx(m.reliability_score)

    def test_high_variance_reduces_reliability(self):
        m = _metrics(total=20, successful=16, variance_coefficient=0.5)
        assert m.variance_adjusted_reliability < m.reliability_score

    def test_low_consistency_reduces_reliability(self):
        m = _metrics(total=20, successful=16, consistency_rate=0.6)
        assert m.variance_adjusted_reliability < m.reliability_score

    def test_variance_coefficient_clamped_at_one(self):
        m = _metrics(total=20, successful=16, variance_coefficient=5.0)
        assert m.variance_adjusted_reliability == pytest.approx(0.0)

    def test_zero_success_rate_gives_zero_adjusted_reliability(self):
        m = _metrics(total=20, successful=0)
        assert m.variance_adjusted_reliability == pytest.approx(0.0)

    def test_formula_applied_correctly(self):
        m = _metrics(total=20, successful=20, variance_coefficient=0.2, consistency_rate=0.8)
        # reliability_score = 1.0 (20/20, >=20 tasks)
        expected = 1.0 * 0.8 * (1.0 - 0.2)
        assert m.variance_adjusted_reliability == pytest.approx(expected)


# ---------------------------------------------------------------------------
# PerformanceAggregator: variance & consistency extraction
# ---------------------------------------------------------------------------

class TestVarianceExtraction:
    def _agg_with_events(self, events: list[dict]) -> PerformanceAggregator:
        store = MagicMock()
        mock_events = []
        for e in events:
            ev = MagicMock()
            ev.payload = e
            ev.timestamp = datetime.now()
            ev.actor_id = "m1"
            mock_events.append(ev)
        store.query.return_value = MagicMock(events=mock_events)
        return PerformanceAggregator(store)

    def test_quality_scores_compute_variance_coefficient(self):
        agg = self._agg_with_events([
            {"success": True, "quality_score": 80},
            {"success": True, "quality_score": 40},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.variance_coefficient > 0.0

    def test_identical_quality_scores_give_zero_variance(self):
        agg = self._agg_with_events([
            {"success": True, "quality_score": 70},
            {"success": True, "quality_score": 70},
            {"success": True, "quality_score": 70},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.variance_coefficient == pytest.approx(0.0)

    def test_single_quality_score_gives_zero_variance(self):
        agg = self._agg_with_events([{"success": True, "quality_score": 60}])
        m = agg.get_agent_metrics("m1")
        assert m.variance_coefficient == pytest.approx(0.0)

    def test_no_quality_score_field_gives_zero_variance(self):
        agg = self._agg_with_events([
            {"success": True},
            {"success": False},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.variance_coefficient == pytest.approx(0.0)

    def test_consistency_rate_perfect_success(self):
        agg = self._agg_with_events([
            {"success": True},
            {"success": True},
            {"success": True},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.consistency_rate == pytest.approx(1.0)

    def test_consistency_rate_fifty_fifty(self):
        agg = self._agg_with_events([
            {"success": True},
            {"success": False},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.consistency_rate == pytest.approx(0.5)

    def test_consistency_rate_mostly_failure(self):
        # 1 success, 3 failures → success_rate=0.25, consistency=max(0.25, 0.75)=0.75
        agg = self._agg_with_events([
            {"success": True},
            {"success": False},
            {"success": False},
            {"success": False},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.consistency_rate == pytest.approx(0.75)

    def test_variance_coefficient_formula(self):
        # scores [60, 100] → mean=80, std≈28.28, vc≈0.354
        agg = self._agg_with_events([
            {"success": True, "quality_score": 60},
            {"success": True, "quality_score": 100},
        ])
        m = agg.get_agent_metrics("m1")
        import statistics as stats
        expected_vc = stats.stdev([60.0, 100.0]) / 80.0
        assert m.variance_coefficient == pytest.approx(expected_vc)


# ---------------------------------------------------------------------------
# MultiRunResult dataclass
# ---------------------------------------------------------------------------

class TestMultiRunResultDataclass:
    def test_fields_accessible(self):
        r = MultiRunResult(
            task_id="t1",
            results=[],
            mean_score=75.0,
            std_dev=10.0,
            variance_coefficient=0.133,
            consistency_rate=0.9,
        )
        assert r.task_id == "t1"
        assert r.mean_score == 75.0
        assert r.variance_coefficient == pytest.approx(0.133)
        assert r.consistency_rate == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# BlindEvaluator.evaluate_multi_run
# ---------------------------------------------------------------------------

class TestEvaluateMultiRun:
    def setup_method(self):
        self.ev = BlindEvaluator()

    def _sub(self, task_id="t1", sid="s1", content="x = 1"):
        return Submission(
            task_id=task_id, submission_id=sid,
            output_type="code", output_content=content,
        )

    def test_empty_submissions_raises(self):
        with pytest.raises(ValueError, match="empty"):
            self.ev.evaluate_multi_run([])

    def test_mixed_task_ids_raises(self):
        s1 = self._sub("t1", "a")
        s2 = self._sub("t2", "b")
        with pytest.raises(ValueError, match="task_id"):
            self.ev.evaluate_multi_run([s1, s2])

    def test_single_submission_returns_result(self):
        result = self.ev.evaluate_multi_run([self._sub()])
        assert isinstance(result, MultiRunResult)
        assert len(result.results) == 1

    def test_task_id_preserved(self):
        result = self.ev.evaluate_multi_run([self._sub(task_id="my-task")])
        assert result.task_id == "my-task"

    def test_mean_score_computed(self):
        # Same content → same score for all runs
        s1 = self._sub(sid="s1")
        s2 = self._sub(sid="s2")
        result = self.ev.evaluate_multi_run([s1, s2])
        expected = (result.results[0].quality_score + result.results[1].quality_score) / 2
        assert result.mean_score == pytest.approx(expected)

    def test_std_dev_zero_for_identical_submissions(self):
        # Same content → deterministic evaluator → same score → std_dev = 0
        subs = [self._sub(sid=f"s{i}") for i in range(3)]
        result = self.ev.evaluate_multi_run(subs)
        assert result.std_dev == pytest.approx(0.0)

    def test_std_dev_nonzero_for_different_content(self):
        good = "def add(a: int, b: int) -> int:\n    '''Add two numbers.'''\n    return a + b"
        bad = "def ??? syntax error"
        s1 = self._sub(sid="s1", content=good)
        s2 = self._sub(sid="s2", content=bad)
        result = self.ev.evaluate_multi_run([s1, s2])
        assert result.std_dev > 0.0

    def test_variance_coefficient_zero_when_identical(self):
        subs = [self._sub(sid=f"s{i}") for i in range(2)]
        result = self.ev.evaluate_multi_run(subs)
        assert result.variance_coefficient == pytest.approx(0.0)

    def test_variance_coefficient_positive_for_different_scores(self):
        good = "def add(a: int, b: int) -> int:\n    '''Add.'''\n    return a + b"
        bad = "def ??? syntax error"
        s1 = self._sub(sid="s1", content=good)
        s2 = self._sub(sid="s2", content=bad)
        result = self.ev.evaluate_multi_run([s1, s2])
        assert result.variance_coefficient > 0.0

    def test_single_submission_std_dev_is_zero(self):
        result = self.ev.evaluate_multi_run([self._sub()])
        assert result.std_dev == pytest.approx(0.0)

    def test_consistency_rate_between_zero_and_one(self):
        subs = [self._sub(sid=f"s{i}") for i in range(3)]
        result = self.ev.evaluate_multi_run(subs)
        assert 0.0 <= result.consistency_rate <= 1.0

    def test_all_results_in_results_list(self):
        subs = [self._sub(sid=f"s{i}") for i in range(4)]
        result = self.ev.evaluate_multi_run(subs)
        assert len(result.results) == 4

    def test_consistency_rate_one_when_all_same_outcome(self):
        # All same content → all same tests_passed value → consistency = 1.0
        subs = [self._sub(sid=f"s{i}") for i in range(3)]
        result = self.ev.evaluate_multi_run(subs)
        assert result.consistency_rate == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Routing: high-variance models penalised
# ---------------------------------------------------------------------------

class TestVarianceAwareRouting:
    def test_high_variance_model_loses_to_consistent_model(self):
        m_consistent = _metrics("consistent", total=20, successful=16,
                                variance_coefficient=0.0, consistency_rate=1.0)
        m_volatile = _metrics("volatile", total=20, successful=16,
                              variance_coefficient=0.8, consistency_rate=0.6)
        broker = _broker({"consistent": m_consistent, "volatile": m_volatile})
        result = broker.route_task()
        assert result.selected_agent == "consistent"

    def test_consistent_model_preferred_even_with_slightly_lower_success_rate(self):
        # consistent: 75% success, no variance penalty
        # volatile: 80% success, heavy variance/consistency penalty
        m_consistent = _metrics("consistent", total=20, successful=15,
                                variance_coefficient=0.0, consistency_rate=1.0)
        m_volatile = _metrics("volatile", total=20, successful=16,
                              variance_coefficient=0.9, consistency_rate=0.55)
        broker = _broker({"consistent": m_consistent, "volatile": m_volatile})
        result = broker.route_task()
        assert result.selected_agent == "consistent"

    def test_zero_variance_no_routing_change_vs_old_behaviour(self):
        # With defaults (variance=0, consistency=1), routing unchanged
        m1 = _metrics("m1", total=20, successful=18)
        m2 = _metrics("m2", total=20, successful=12)
        broker = _broker({"m1": m1, "m2": m2})
        result = broker.route_task()
        assert result.selected_agent == "m1"
