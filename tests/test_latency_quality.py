"""Tests for latency-quality correlation analysis (ace_enterprise-5cm)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.broker.adaptive_broker import AdaptiveBroker, BrokerConfig
from src.broker.performance_aggregator import (
    AgentPerformanceMetrics,
    LatencyQualityReport,
    PerformanceAggregator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _metrics(
    agent_ref="m",
    total=20,
    successful=16,
    avg_latency: float = 0.0,
    latency_p50: float = 0.0,
    latency_p95: float = 0.0,
    correlation: float | None = None,
    tier_latencies: dict[str, float] | None = None,
) -> AgentPerformanceMetrics:
    m = AgentPerformanceMetrics(agent_ref=agent_ref)
    m.total_tasks = total
    m.successful_tasks = successful
    m.failed_tasks = total - successful
    m.avg_latency_seconds = avg_latency
    m.latency_p50_seconds = latency_p50
    m.latency_p95_seconds = latency_p95
    m.latency_quality_correlation = correlation
    m.latency_p50_by_quality_tier = tier_latencies or {}
    return m


def _broker(
    metrics_map: dict[str, AgentPerformanceMetrics],
    config: BrokerConfig | None = None,
) -> AdaptiveBroker:
    store = MagicMock()
    store.query.return_value = MagicMock(events=[])
    agg = PerformanceAggregator(store)
    agg._cache = metrics_map
    agg._cache_expiry = datetime.now() + timedelta(minutes=5)
    return AdaptiveBroker(agg, config=config)


def _agg_with_events(events: list[dict]) -> PerformanceAggregator:
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


def _agg_with_cache(metrics_map: dict[str, AgentPerformanceMetrics]) -> PerformanceAggregator:
    store = MagicMock()
    store.query.return_value = MagicMock(events=[])
    agg = PerformanceAggregator(store)
    agg._cache = metrics_map
    agg._cache_expiry = datetime.now() + timedelta(minutes=5)
    return agg


# ---------------------------------------------------------------------------
# AgentPerformanceMetrics new fields
# ---------------------------------------------------------------------------

class TestNewMetricsFields:
    def test_default_correlation_is_none(self):
        m = AgentPerformanceMetrics(agent_ref="m")
        assert m.latency_quality_correlation is None

    def test_default_p50_is_zero(self):
        m = AgentPerformanceMetrics(agent_ref="m")
        assert m.latency_p50_seconds == 0.0

    def test_default_p95_is_zero(self):
        m = AgentPerformanceMetrics(agent_ref="m")
        assert m.latency_p95_seconds == 0.0

    def test_default_tier_dict_empty(self):
        m = AgentPerformanceMetrics(agent_ref="m")
        assert m.latency_p50_by_quality_tier == {}


# ---------------------------------------------------------------------------
# PerformanceAggregator._percentile
# ---------------------------------------------------------------------------

class TestPercentile:
    def test_empty_returns_zero(self):
        assert PerformanceAggregator._percentile([], 50) == 0.0

    def test_single_element_returns_it(self):
        assert PerformanceAggregator._percentile([5.0], 50) == pytest.approx(5.0)

    def test_p50_of_even_list(self):
        # [1,2,3,4] → idx=2 → 3
        result = PerformanceAggregator._percentile([4.0, 1.0, 3.0, 2.0], 50)
        assert result == pytest.approx(3.0)

    def test_p0_returns_minimum(self):
        assert PerformanceAggregator._percentile([5.0, 1.0, 3.0], 0) == pytest.approx(1.0)

    def test_p100_clamps_to_last(self):
        result = PerformanceAggregator._percentile([1.0, 2.0, 3.0], 100)
        assert result == pytest.approx(3.0)

    def test_p95_of_larger_list(self):
        data = list(range(1, 21))  # 1..20
        p95 = PerformanceAggregator._percentile([float(x) for x in data], 95)
        assert p95 >= 18.0  # near the top


# ---------------------------------------------------------------------------
# _aggregate_metrics: latency/quality extraction
# ---------------------------------------------------------------------------

class TestAggregateLatencyQuality:
    def test_p50_computed_from_latencies(self):
        agg = _agg_with_events([
            {"success": True, "elapsed_seconds": 1.0},
            {"success": True, "elapsed_seconds": 3.0},
            {"success": True, "elapsed_seconds": 2.0},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.latency_p50_seconds > 0.0

    def test_p95_greater_than_or_equal_p50(self):
        agg = _agg_with_events([
            {"success": True, "elapsed_seconds": float(i)} for i in range(1, 11)
        ])
        m = agg.get_agent_metrics("m1")
        assert m.latency_p95_seconds >= m.latency_p50_seconds

    def test_correlation_computed_when_both_present(self):
        agg = _agg_with_events([
            {"success": True, "elapsed_seconds": 1.0, "quality_score": 90},
            {"success": True, "elapsed_seconds": 2.0, "quality_score": 70},
            {"success": True, "elapsed_seconds": 3.0, "quality_score": 50},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.latency_quality_correlation is not None

    def test_negative_correlation_when_slower_means_worse(self):
        # higher latency → lower quality → negative Pearson r
        agg = _agg_with_events([
            {"success": True, "elapsed_seconds": 1.0, "quality_score": 90},
            {"success": True, "elapsed_seconds": 2.0, "quality_score": 70},
            {"success": True, "elapsed_seconds": 3.0, "quality_score": 50},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.latency_quality_correlation < 0

    def test_positive_correlation_when_slower_means_better(self):
        # higher latency → higher quality (model "thinks" longer)
        agg = _agg_with_events([
            {"success": True, "elapsed_seconds": 1.0, "quality_score": 40},
            {"success": True, "elapsed_seconds": 2.0, "quality_score": 70},
            {"success": True, "elapsed_seconds": 3.0, "quality_score": 90},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.latency_quality_correlation > 0

    def test_correlation_none_with_only_one_pair(self):
        agg = _agg_with_events([
            {"success": True, "elapsed_seconds": 1.0, "quality_score": 80},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.latency_quality_correlation is None

    def test_correlation_none_without_quality_scores(self):
        agg = _agg_with_events([
            {"success": True, "elapsed_seconds": 1.0},
            {"success": True, "elapsed_seconds": 2.0},
        ])
        m = agg.get_agent_metrics("m1")
        assert m.latency_quality_correlation is None

    def test_tier_breakdown_populated(self):
        agg = _agg_with_events([
            {"success": True, "elapsed_seconds": 1.0, "quality_score": 20},   # low
            {"success": True, "elapsed_seconds": 2.0, "quality_score": 60},   # mid
            {"success": True, "elapsed_seconds": 3.0, "quality_score": 85},   # high
        ])
        m = agg.get_agent_metrics("m1")
        assert "low" in m.latency_p50_by_quality_tier
        assert "mid" in m.latency_p50_by_quality_tier
        assert "high" in m.latency_p50_by_quality_tier

    def test_tier_empty_when_no_matching_quality(self):
        # all scores are "high" → no low/mid tier
        agg = _agg_with_events([
            {"success": True, "elapsed_seconds": 1.0, "quality_score": 80},
            {"success": True, "elapsed_seconds": 2.0, "quality_score": 90},
        ])
        m = agg.get_agent_metrics("m1")
        assert "low" not in m.latency_p50_by_quality_tier
        assert "mid" not in m.latency_p50_by_quality_tier
        assert "high" in m.latency_p50_by_quality_tier

    def test_correlation_bounded_minus_one_to_one(self):
        agg = _agg_with_events([
            {"success": True, "elapsed_seconds": float(i), "quality_score": float(i * 10)}
            for i in range(1, 6)
        ])
        m = agg.get_agent_metrics("m1")
        if m.latency_quality_correlation is not None:
            assert -1.0 <= m.latency_quality_correlation <= 1.0


# ---------------------------------------------------------------------------
# LatencyQualityReport dataclass
# ---------------------------------------------------------------------------

class TestLatencyQualityReport:
    def test_fields_accessible(self):
        r = LatencyQualityReport(
            agent_ref="m1",
            latency_quality_correlation=-0.7,
            latency_p50_seconds=1.2,
            latency_p95_seconds=3.5,
            latency_p50_by_quality_tier={"high": 1.0},
            sample_count=50,
        )
        assert r.agent_ref == "m1"
        assert r.latency_quality_correlation == pytest.approx(-0.7)
        assert r.latency_p50_seconds == pytest.approx(1.2)
        assert r.sample_count == 50


# ---------------------------------------------------------------------------
# PerformanceAggregator: get_latency_quality_report / get_all / fastest
# ---------------------------------------------------------------------------

class TestLatencyQualityMethods:
    def test_get_report_returns_latency_quality_report(self):
        m = _metrics("m1", avg_latency=1.5, latency_p50=1.2)
        agg = _agg_with_cache({"m1": m})
        report = agg.get_latency_quality_report("m1")
        assert isinstance(report, LatencyQualityReport)

    def test_get_report_agent_ref_correct(self):
        m = _metrics("m1")
        agg = _agg_with_cache({"m1": m})
        assert agg.get_latency_quality_report("m1").agent_ref == "m1"

    def test_get_report_sample_count(self):
        m = _metrics("m1", total=42)
        agg = _agg_with_cache({"m1": m})
        assert agg.get_latency_quality_report("m1").sample_count == 42

    def test_get_all_returns_dict(self):
        agg = _agg_with_cache({"m1": _metrics("m1"), "m2": _metrics("m2")})
        reports = agg.get_all_latency_quality_reports()
        assert set(reports.keys()) == {"m1", "m2"}
        assert all(isinstance(r, LatencyQualityReport) for r in reports.values())

    def test_get_all_empty_when_no_agents(self):
        agg = _agg_with_cache({})
        assert agg.get_all_latency_quality_reports() == {}

    def test_fastest_returns_lowest_latency_above_threshold(self):
        m_fast = _metrics("fast", total=20, successful=16, avg_latency=0.5)
        m_slow = _metrics("slow", total=20, successful=16, avg_latency=2.0)
        agg = _agg_with_cache({"fast": m_fast, "slow": m_slow})
        assert agg.fastest_model_meeting_quality(0.5) == "fast"

    def test_fastest_filters_below_quality_threshold(self):
        m_fast = _metrics("fast", total=20, successful=8, avg_latency=0.5)   # 40% quality
        m_slow = _metrics("slow", total=20, successful=16, avg_latency=2.0)  # 80% quality
        agg = _agg_with_cache({"fast": m_fast, "slow": m_slow})
        assert agg.fastest_model_meeting_quality(0.7) == "slow"

    def test_fastest_returns_none_when_none_qualify(self):
        m = _metrics("m1", total=20, successful=5, avg_latency=1.0)  # 25%
        agg = _agg_with_cache({"m1": m})
        assert agg.fastest_model_meeting_quality(0.8) is None

    def test_fastest_excludes_zero_latency_agents(self):
        # zero latency means no data — excluded
        m_no_data = _metrics("nodata", total=20, successful=20, avg_latency=0.0)
        m_real = _metrics("real", total=20, successful=20, avg_latency=1.0)
        agg = _agg_with_cache({"nodata": m_no_data, "real": m_real})
        result = agg.fastest_model_meeting_quality(0.5)
        assert result == "real"

    def test_fastest_restricted_to_agent_refs(self):
        m1 = _metrics("m1", total=20, successful=16, avg_latency=0.5)
        m2 = _metrics("m2", total=20, successful=16, avg_latency=1.0)
        agg = _agg_with_cache({"m1": m1, "m2": m2})
        result = agg.fastest_model_meeting_quality(0.5, agent_refs=["m2"])
        assert result == "m2"


# ---------------------------------------------------------------------------
# BrokerConfig.max_latency_seconds
# ---------------------------------------------------------------------------

class TestBrokerConfigLatency:
    def test_default_max_latency_is_none(self):
        assert BrokerConfig().max_latency_seconds is None

    def test_custom_max_latency_stored(self):
        cfg = BrokerConfig(max_latency_seconds=2.0)
        assert cfg.max_latency_seconds == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# AdaptiveBroker latency-constrained routing
# ---------------------------------------------------------------------------

class TestLatencyConstrainedRouting:
    def test_filters_agent_exceeding_latency_cap(self):
        m_fast = _metrics("fast", total=20, successful=12, avg_latency=0.5)  # 60%
        m_slow = _metrics("slow", total=20, successful=18, avg_latency=5.0)  # 90%
        cfg = BrokerConfig(max_latency_seconds=1.0)
        broker = _broker({"fast": m_fast, "slow": m_slow}, config=cfg)
        result = broker.route_task()
        assert result.selected_agent == "fast"

    def test_selects_best_quality_within_latency_cap(self):
        m1 = _metrics("m1", total=20, successful=14, avg_latency=0.8)  # 70%
        m2 = _metrics("m2", total=20, successful=16, avg_latency=0.9)  # 80%
        m3 = _metrics("m3", total=20, successful=18, avg_latency=5.0)  # 90% over cap
        cfg = BrokerConfig(max_latency_seconds=1.0)
        broker = _broker({"m1": m1, "m2": m2, "m3": m3}, config=cfg)
        result = broker.route_task()
        assert result.selected_agent == "m2"

    def test_no_cap_all_agents_considered(self):
        m_fast = _metrics("fast", total=20, successful=12, avg_latency=0.1)
        m_slow = _metrics("slow", total=20, successful=18, avg_latency=10.0)
        broker = _broker({"fast": m_fast, "slow": m_slow})
        result = broker.route_task()
        assert result.selected_agent == "slow"  # no cap → quality wins

    def test_agents_with_no_latency_data_not_filtered(self):
        m_unknown = _metrics("unknown", total=20, successful=16, avg_latency=0.0)
        m_fast = _metrics("fast", total=20, successful=14, avg_latency=0.5)
        cfg = BrokerConfig(max_latency_seconds=1.0)
        broker = _broker({"unknown": m_unknown, "fast": m_fast}, config=cfg)
        result = broker.route_task()
        assert result.selected_agent in ("unknown", "fast")

    def test_fallback_when_all_exceed_cap(self):
        m1 = _metrics("m1", total=20, successful=16, avg_latency=5.0)
        m2 = _metrics("m2", total=20, successful=12, avg_latency=8.0)
        cfg = BrokerConfig(max_latency_seconds=0.1)
        broker = _broker({"m1": m1, "m2": m2}, config=cfg)
        # All exceed cap → falls back to full list
        result = broker.route_task()
        assert result.selected_agent in ("m1", "m2")

    def test_latency_filter_and_cost_mode_combined(self):
        from src.broker.adaptive_broker import ROUTING_BUDGET
        m1 = _metrics("m1", total=20, successful=16, avg_latency=0.5)
        m1.avg_cost_per_task = 0.05
        m2 = _metrics("m2", total=20, successful=14, avg_latency=0.8)
        m2.avg_cost_per_task = 0.08
        m3 = _metrics("m3", total=20, successful=18, avg_latency=5.0)
        m3.avg_cost_per_task = 0.03
        cfg = BrokerConfig(
            routing_mode=ROUTING_BUDGET,
            max_cost_per_task=0.10,
            max_latency_seconds=1.0,
        )
        broker = _broker({"m1": m1, "m2": m2, "m3": m3}, config=cfg)
        result = broker.route_task()
        # m3 filtered by latency; m1 and m2 within budget → best quality = m1 (80%)
        assert result.selected_agent == "m1"
