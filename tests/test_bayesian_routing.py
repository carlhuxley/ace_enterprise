"""Tests for Bayesian confidence-interval routing (ace_enterprise-2uq)."""

import pytest

from src.broker.bayesian import (
    INSUFFICIENT_DATA_THRESHOLD,
    BayesianEstimate,
    estimate_success_rate,
)
from src.broker.performance_aggregator import AgentPerformanceMetrics


# ---------------------------------------------------------------------------
# estimate_success_rate unit tests
# ---------------------------------------------------------------------------


def test_posterior_mean_uniform_prior():
    est = estimate_success_rate(7, 3)
    # alpha_post=8, beta_post=4 → mean = 8/12 = 0.6667
    assert abs(est.mean - 8 / 12) < 1e-9


def test_posterior_mean_informative_prior():
    est = estimate_success_rate(5, 5, prior_alpha=2.0, prior_beta=2.0)
    # alpha_post=7, beta_post=7 → mean = 0.5
    assert abs(est.mean - 0.5) < 1e-9


def test_ci_bounds_ordered():
    est = estimate_success_rate(10, 2)
    assert est.ci_lower < est.mean < est.ci_upper


def test_ci_width_computed_correctly():
    est = estimate_success_rate(5, 5)
    assert abs(est.ci_width - (est.ci_upper - est.ci_lower)) < 1e-12


def test_insufficient_data_zero_observations():
    est = estimate_success_rate(0, 0)
    # Beta(1,1) → CI nearly 0–1 → wide → insufficient
    assert est.is_insufficient_data is True


def test_insufficient_data_flag_set_when_wide():
    est = estimate_success_rate(1, 0)
    assert est.ci_width > INSUFFICIENT_DATA_THRESHOLD
    assert est.is_insufficient_data is True


def test_sufficient_data_flag_cleared():
    est = estimate_success_rate(50, 10)
    assert est.is_insufficient_data is False


def test_ci_narrows_with_more_data():
    sparse = estimate_success_rate(2, 1)
    dense = estimate_success_rate(200, 100)
    assert dense.ci_width < sparse.ci_width


def test_alpha_beta_posterior_stored():
    est = estimate_success_rate(7, 3, prior_alpha=2.0, prior_beta=1.0)
    assert est.alpha_posterior == 9.0
    assert est.beta_posterior == 4.0


def test_confidence_level_stored():
    est = estimate_success_rate(10, 5, confidence_level=0.80)
    assert est.confidence_level == 0.80


def test_lower_confidence_gives_narrower_ci():
    est90 = estimate_success_rate(10, 5, confidence_level=0.90)
    est99 = estimate_success_rate(10, 5, confidence_level=0.99)
    assert est90.ci_width < est99.ci_width


def test_ci_lower_is_conservative():
    """ci_lower is always below the posterior mean — conservative routing score."""
    for s, f in [(1, 0), (5, 5), (20, 2), (0, 5)]:
        est = estimate_success_rate(s, f)
        assert est.ci_lower <= est.mean


# ---------------------------------------------------------------------------
# AgentPerformanceMetrics integration
# ---------------------------------------------------------------------------


def _make_metrics(successful: int, failed: int, **kwargs) -> AgentPerformanceMetrics:
    m = AgentPerformanceMetrics(
        agent_ref="test-agent",
        total_tasks=successful + failed,
        successful_tasks=successful,
        failed_tasks=failed,
        **kwargs,
    )
    from src.broker.bayesian import estimate_success_rate as _est
    m.bayesian_estimate = _est(successful, failed)
    return m


def test_metrics_bayesian_estimate_populated():
    m = _make_metrics(8, 2)
    assert m.bayesian_estimate is not None
    assert isinstance(m.bayesian_estimate, BayesianEstimate)


def test_metrics_bayesian_estimate_mean_consistent_with_success_rate():
    m = _make_metrics(8, 2)
    # alpha_post = 1+8 = 9, beta_post = 1+2 = 3 → mean = 9/12 = 0.75
    assert abs(m.bayesian_estimate.mean - 9 / 12) < 1e-9


# ---------------------------------------------------------------------------
# AdaptiveBroker._calculate_score uses Bayesian CI lower bound
# ---------------------------------------------------------------------------


class _FakeAggregator:
    """Minimal aggregator stub for broker tests."""

    def __init__(self, metrics_map: dict):
        self._map = metrics_map

    def get_all_agent_metrics(self):
        return self._map

    def get_all_model_profiles(self):
        return {}

    def invalidate_cache(self):
        pass


def _broker_with_agents(agents: dict[str, AgentPerformanceMetrics]):
    from src.broker.adaptive_broker import AdaptiveBroker, BrokerConfig
    agg = _FakeAggregator(agents)
    return AdaptiveBroker(agg, BrokerConfig())


def test_sparse_agent_scored_lower_than_dense_equal_rate():
    """Agent with 3 tasks should score lower than one with 50 tasks at same rate."""
    sparse = _make_metrics(2, 1)   # 67% with 3 tasks
    dense = _make_metrics(33, 17)  # 66% with 50 tasks

    broker = _broker_with_agents({"sparse": sparse, "dense": dense})

    # Extract calculated scores via route_task
    result = broker.route_task()
    scores = dict(result.candidates)
    assert scores["dense"] > scores["sparse"]


def test_broker_selects_reliable_over_sparse():
    reliable = _make_metrics(40, 5)  # 89% success, many tasks
    uncertain = _make_metrics(1, 0)  # 100% but 1 task only

    broker = _broker_with_agents({"reliable": reliable, "uncertain": uncertain})
    result = broker.route_task()
    assert result.selected_agent == "reliable"


def test_zero_task_agent_falls_back_to_variance_adjusted():
    """Agent with no tasks uses variance_adjusted_reliability (Bayesian still set)."""
    m = AgentPerformanceMetrics(agent_ref="new-agent")
    from src.broker.bayesian import estimate_success_rate as _est
    m.bayesian_estimate = _est(0, 0)

    broker = _broker_with_agents({"new": m})
    result = broker.route_task()
    # Should not raise; fallback path used since total_tasks==0
    assert result.selected_agent in ("new", "default-agent")


# ---------------------------------------------------------------------------
# PerformanceAggregator convenience methods
# ---------------------------------------------------------------------------


def _aggregator_with_mock_store(successful: int, failed: int):
    """Build a PerformanceAggregator whose store returns synthetic events."""
    from unittest.mock import MagicMock
    from datetime import datetime, UTC

    from src.broker.performance_aggregator import PerformanceAggregator
    from src.audit.schemas import AuditEventType

    events = []
    for i in range(successful):
        ev = MagicMock()
        ev.actor_id = "agent-a"
        ev.timestamp = datetime.now(UTC)
        ev.payload = {"success": True, "elapsed_seconds": 1.0}
        events.append(ev)
    for i in range(failed):
        ev = MagicMock()
        ev.actor_id = "agent-a"
        ev.timestamp = datetime.now(UTC)
        ev.payload = {"success": False, "elapsed_seconds": 1.0}
        events.append(ev)

    store = MagicMock()
    result = MagicMock()
    result.events = events
    store.query.return_value = result

    return PerformanceAggregator(store)


def test_compute_bayesian_estimate_returns_estimate():
    agg = _aggregator_with_mock_store(8, 2)
    est = agg.compute_bayesian_estimate("agent-a")
    assert est is not None
    assert isinstance(est, BayesianEstimate)


def test_get_all_bayesian_estimates_keys_match_agents():
    agg = _aggregator_with_mock_store(8, 2)
    estimates = agg.get_all_bayesian_estimates()
    assert "agent-a" in estimates
    assert isinstance(estimates["agent-a"], BayesianEstimate)
