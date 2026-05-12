"""Tests for cost-aware routing modes in AdaptiveBroker (ace_enterprise-17z)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.broker.adaptive_broker import (
    ROUTING_BALANCED,
    ROUTING_BEST_QUALITY,
    ROUTING_BUDGET,
    ROUTING_PARETO,
    AdaptiveBroker,
    BrokerConfig,
)
from src.broker.performance_aggregator import (
    AgentPerformanceMetrics,
    PerformanceAggregator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _metrics(
    agent_ref="m",
    total=20,
    successful=16,
    avg_cost: float = 0.0,
    task_types: dict[str, float] | None = None,
) -> AgentPerformanceMetrics:
    m = AgentPerformanceMetrics(agent_ref=agent_ref)
    m.total_tasks = total
    m.successful_tasks = successful
    m.failed_tasks = total - successful
    m.avg_cost_per_task = avg_cost
    m.total_cost = avg_cost * total
    m.success_by_task_type = task_types or {}
    return m


def _broker(metrics_map: dict[str, AgentPerformanceMetrics], config: BrokerConfig | None = None) -> AdaptiveBroker:
    store = MagicMock()
    store.query.return_value = MagicMock(events=[])
    agg = PerformanceAggregator(store)
    agg._cache = metrics_map
    agg._cache_expiry = datetime.now() + timedelta(minutes=5)
    return AdaptiveBroker(agg, config=config)


# ---------------------------------------------------------------------------
# BrokerConfig cost fields
# ---------------------------------------------------------------------------

class TestBrokerConfigCostFields:
    def test_default_routing_mode_is_best_quality(self):
        assert BrokerConfig().routing_mode == ROUTING_BEST_QUALITY

    def test_default_max_cost_is_none(self):
        assert BrokerConfig().max_cost_per_task is None

    def test_default_cost_quality_tradeoff(self):
        assert BrokerConfig().cost_quality_tradeoff == 0.5

    def test_default_acceptable_quality_delta(self):
        assert BrokerConfig().acceptable_quality_delta == 0.05

    def test_custom_routing_mode(self):
        cfg = BrokerConfig(routing_mode=ROUTING_BUDGET)
        assert cfg.routing_mode == ROUTING_BUDGET

    def test_custom_max_cost(self):
        cfg = BrokerConfig(max_cost_per_task=0.10)
        assert cfg.max_cost_per_task == 0.10


# ---------------------------------------------------------------------------
# PerformanceAggregator cost extraction from audit events
# ---------------------------------------------------------------------------

class TestCostExtraction:
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
        agg = PerformanceAggregator(store)
        return agg

    def test_cost_extracted_from_payload(self):
        agg = self._agg_with_events([
            {"success": True, "cost": 0.02},
            {"success": True, "cost": 0.04},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.total_cost == pytest.approx(0.06)

    def test_avg_cost_computed(self):
        agg = self._agg_with_events([
            {"success": True, "cost": 0.02},
            {"success": True, "cost": 0.04},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.avg_cost_per_task == pytest.approx(0.03)

    def test_missing_cost_field_not_counted(self):
        agg = self._agg_with_events([
            {"success": True},
            {"success": True},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.total_cost == 0.0
        assert m.avg_cost_per_task == 0.0

    def test_zero_cost_not_affects_avg(self):
        agg = self._agg_with_events([
            {"success": True, "cost": 0.0},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.avg_cost_per_task == 0.0

    def test_mixed_with_and_without_cost(self):
        agg = self._agg_with_events([
            {"success": True, "cost": 0.06},
            {"success": True},  # no cost key
        ])
        m = agg.get_agent_metrics("m1")
        # total_cost = 0.06, total_tasks = 2
        assert m.total_cost == pytest.approx(0.06)
        assert m.avg_cost_per_task == pytest.approx(0.03)


# ---------------------------------------------------------------------------
# BEST_QUALITY mode (default — cost ignored)
# ---------------------------------------------------------------------------

class TestBestQualityMode:
    def test_selects_highest_quality_regardless_of_cost(self):
        m_cheap = _metrics("cheap", total=20, successful=10, avg_cost=0.01)  # 50% quality
        m_expensive = _metrics("expensive", total=20, successful=18, avg_cost=1.00)  # 90%
        broker = _broker({"cheap": m_cheap, "expensive": m_expensive})
        result = broker.route_task()
        assert result.selected_agent == "expensive"

    def test_cost_has_no_effect_in_best_quality_mode(self):
        m1 = _metrics("m1", total=20, successful=16, avg_cost=100.0)  # same quality
        m2 = _metrics("m2", total=20, successful=16, avg_cost=0.001)
        cfg = BrokerConfig(routing_mode=ROUTING_BEST_QUALITY)
        broker = _broker({"m1": m1, "m2": m2}, config=cfg)
        result = broker.route_task()
        # Both same quality, order undetermined but should return one of them
        assert result.selected_agent in ("m1", "m2")


# ---------------------------------------------------------------------------
# BUDGET mode
# ---------------------------------------------------------------------------

class TestBudgetMode:
    def test_filters_agents_exceeding_cap(self):
        cheap = _metrics("cheap", total=20, successful=12, avg_cost=0.05)  # 60%
        expensive = _metrics("expensive", total=20, successful=18, avg_cost=0.50)  # 90%
        cfg = BrokerConfig(routing_mode=ROUTING_BUDGET, max_cost_per_task=0.10)
        broker = _broker({"cheap": cheap, "expensive": expensive}, config=cfg)
        result = broker.route_task()
        assert result.selected_agent == "cheap"

    def test_selects_best_quality_within_budget(self):
        m1 = _metrics("m1", total=20, successful=14, avg_cost=0.05)  # 70%
        m2 = _metrics("m2", total=20, successful=16, avg_cost=0.08)  # 80%
        m3 = _metrics("m3", total=20, successful=18, avg_cost=0.50)  # 90% over budget
        cfg = BrokerConfig(routing_mode=ROUTING_BUDGET, max_cost_per_task=0.10)
        broker = _broker({"m1": m1, "m2": m2, "m3": m3}, config=cfg)
        result = broker.route_task()
        assert result.selected_agent == "m2"

    def test_fallback_to_cheapest_when_all_exceed_cap(self):
        m1 = _metrics("m1", total=20, successful=16, avg_cost=1.00)
        m2 = _metrics("m2", total=20, successful=18, avg_cost=2.00)
        cfg = BrokerConfig(routing_mode=ROUTING_BUDGET, max_cost_per_task=0.01)
        broker = _broker({"m1": m1, "m2": m2}, config=cfg)
        result = broker.route_task()
        assert result.selected_agent == "m1"  # cheapest

    def test_no_cap_returns_all_candidates(self):
        m1 = _metrics("m1", total=20, successful=14, avg_cost=0.50)
        m2 = _metrics("m2", total=20, successful=18, avg_cost=1.00)
        cfg = BrokerConfig(routing_mode=ROUTING_BUDGET, max_cost_per_task=None)
        broker = _broker({"m1": m1, "m2": m2}, config=cfg)
        result = broker.route_task()
        assert result.selected_agent == "m2"

    def test_agent_at_exact_cap_is_included(self):
        m = _metrics("m", total=20, successful=16, avg_cost=0.10)
        cfg = BrokerConfig(routing_mode=ROUTING_BUDGET, max_cost_per_task=0.10)
        broker = _broker({"m": m}, config=cfg)
        result = broker.route_task()
        assert result.selected_agent == "m"


# ---------------------------------------------------------------------------
# BALANCED mode
# ---------------------------------------------------------------------------

class TestBalancedMode:
    def test_quality_biased_tradeoff_prefers_quality(self):
        cheap_low = _metrics("cheap_low", total=20, successful=10, avg_cost=0.01)  # 50% quality
        expensive_high = _metrics("exp_high", total=20, successful=18, avg_cost=1.00)  # 90% quality
        cfg = BrokerConfig(routing_mode=ROUTING_BALANCED, cost_quality_tradeoff=0.9)
        broker = _broker({"cheap_low": cheap_low, "exp_high": expensive_high}, config=cfg)
        result = broker.route_task()
        assert result.selected_agent == "exp_high"

    def test_cost_biased_tradeoff_prefers_cheap(self):
        cheap_low = _metrics("cheap_low", total=20, successful=10, avg_cost=0.01)  # 50%
        expensive_high = _metrics("exp_high", total=20, successful=18, avg_cost=1.00)  # 90%
        cfg = BrokerConfig(routing_mode=ROUTING_BALANCED, cost_quality_tradeoff=0.1)
        broker = _broker({"cheap_low": cheap_low, "exp_high": expensive_high}, config=cfg)
        result = broker.route_task()
        assert result.selected_agent == "cheap_low"

    def test_balanced_score_between_zero_and_one(self):
        store = MagicMock()
        store.query.return_value = MagicMock(events=[])
        agg = PerformanceAggregator(store)
        broker = AdaptiveBroker(agg, config=BrokerConfig())
        m1 = _metrics("m1", avg_cost=0.05)
        m2 = _metrics("m2", avg_cost=0.20)
        candidates = [("m1", 0.8), ("m2", 0.6)]
        result = broker._apply_balanced_mode(candidates, {"m1": m1, "m2": m2})
        for _, score in result:
            assert 0.0 <= score <= 1.0

    def test_all_zero_cost_uses_quality_only(self):
        m1 = _metrics("m1", total=20, successful=16, avg_cost=0.0)
        m2 = _metrics("m2", total=20, successful=10, avg_cost=0.0)
        cfg = BrokerConfig(routing_mode=ROUTING_BALANCED, cost_quality_tradeoff=0.5)
        broker = _broker({"m1": m1, "m2": m2}, config=cfg)
        result = broker.route_task()
        assert result.selected_agent == "m1"

    def test_tradeoff_zero_makes_all_cost_scores_equal_when_cost_zero(self):
        store = MagicMock()
        store.query.return_value = MagicMock(events=[])
        agg = PerformanceAggregator(store)
        broker = AdaptiveBroker(agg, config=BrokerConfig(cost_quality_tradeoff=0.0))
        m1 = _metrics("m1", avg_cost=0.0)
        m2 = _metrics("m2", avg_cost=0.0)
        candidates = [("m1", 0.9), ("m2", 0.5)]
        result = broker._apply_balanced_mode(candidates, {"m1": m1, "m2": m2})
        # cost_score = 1.0 for both (max_cost=0), q_weight=0 → both score 1.0
        scores = {ref: score for ref, score in result}
        assert scores["m1"] == pytest.approx(1.0)
        assert scores["m2"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# PARETO mode
# ---------------------------------------------------------------------------

class TestParetoMode:
    def test_dominated_agent_excluded_from_frontier(self):
        # m_dom is dominated by m_good (higher quality, lower cost)
        m_good = _metrics("m_good", total=20, successful=18, avg_cost=0.10)   # quality=0.9, cost=0.10
        m_dom = _metrics("m_dom", total=20, successful=14, avg_cost=0.20)     # quality=0.7, cost=0.20
        store = MagicMock()
        store.query.return_value = MagicMock(events=[])
        agg = PerformanceAggregator(store)
        broker = AdaptiveBroker(agg, config=BrokerConfig())
        candidates = [("m_good", 0.9), ("m_dom", 0.7)]
        metrics_map = {"m_good": m_good, "m_dom": m_dom}
        frontier = broker._get_pareto_frontier(candidates, metrics_map)
        refs = [r for r, _ in frontier]
        assert "m_good" in refs
        assert "m_dom" not in refs

    def test_non_dominated_agents_both_on_frontier(self):
        # m_fast: high quality, high cost; m_cheap: lower quality, lower cost
        m_fast = _metrics("m_fast", total=20, successful=18, avg_cost=1.00)
        m_cheap = _metrics("m_cheap", total=20, successful=12, avg_cost=0.05)
        store = MagicMock()
        store.query.return_value = MagicMock(events=[])
        agg = PerformanceAggregator(store)
        broker = AdaptiveBroker(agg, config=BrokerConfig())
        candidates = [("m_fast", 0.9), ("m_cheap", 0.6)]
        metrics_map = {"m_fast": m_fast, "m_cheap": m_cheap}
        frontier = broker._get_pareto_frontier(candidates, metrics_map)
        refs = [r for r, _ in frontier]
        assert "m_fast" in refs
        assert "m_cheap" in refs

    def test_pareto_quality_biased_selects_high_quality(self):
        m_fast = _metrics("m_fast", total=20, successful=18, avg_cost=1.00)
        m_cheap = _metrics("m_cheap", total=20, successful=12, avg_cost=0.05)
        cfg = BrokerConfig(routing_mode=ROUTING_PARETO, cost_quality_tradeoff=0.9)
        broker = _broker({"m_fast": m_fast, "m_cheap": m_cheap}, config=cfg)
        result = broker.route_task()
        assert result.selected_agent == "m_fast"

    def test_pareto_cost_biased_selects_cheap(self):
        m_fast = _metrics("m_fast", total=20, successful=18, avg_cost=1.00)
        m_cheap = _metrics("m_cheap", total=20, successful=12, avg_cost=0.05)
        cfg = BrokerConfig(routing_mode=ROUTING_PARETO, cost_quality_tradeoff=0.1)
        broker = _broker({"m_fast": m_fast, "m_cheap": m_cheap}, config=cfg)
        result = broker.route_task()
        assert result.selected_agent == "m_cheap"

    def test_single_agent_always_on_frontier(self):
        m = _metrics("solo", total=20, successful=16, avg_cost=0.50)
        store = MagicMock()
        store.query.return_value = MagicMock(events=[])
        agg = PerformanceAggregator(store)
        broker = AdaptiveBroker(agg, config=BrokerConfig())
        frontier = broker._get_pareto_frontier([("solo", 0.8)], {"solo": m})
        assert len(frontier) == 1
        assert frontier[0][0] == "solo"

    def test_pareto_scores_clamped_to_one(self):
        m_fast = _metrics("m_fast", total=20, successful=18, avg_cost=0.0)
        m_cheap = _metrics("m_cheap", total=20, successful=12, avg_cost=0.0)
        cfg = BrokerConfig(routing_mode=ROUTING_PARETO, cost_quality_tradeoff=0.5)
        broker = _broker({"m_fast": m_fast, "m_cheap": m_cheap}, config=cfg)
        result = broker.route_task()
        for _, score in result.candidates:
            assert score <= 1.0


# ---------------------------------------------------------------------------
# Routing mode constants
# ---------------------------------------------------------------------------

class TestRoutingModeConstants:
    def test_constants_are_strings(self):
        assert isinstance(ROUTING_BEST_QUALITY, str)
        assert isinstance(ROUTING_BUDGET, str)
        assert isinstance(ROUTING_BALANCED, str)
        assert isinstance(ROUTING_PARETO, str)

    def test_constants_are_distinct(self):
        modes = {ROUTING_BEST_QUALITY, ROUTING_BUDGET, ROUTING_BALANCED, ROUTING_PARETO}
        assert len(modes) == 4
