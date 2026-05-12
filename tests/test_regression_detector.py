"""Tests for regression detection when OpenRouter models update (ace_enterprise-qo1)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.broker.regression_detector import (
    REGRESSION_THRESHOLD,
    WARNING_THRESHOLD,
    QualityBaseline,
    RegressionAlert,
    RegressionDetector,
)
from src.broker.performance_aggregator import AgentPerformanceMetrics, PerformanceAggregator
from src.utils.llm_client import extract_model_version


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detector(**kwargs) -> RegressionDetector:
    return RegressionDetector(**kwargs)


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
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_regression_threshold_is_15_percent(self):
        assert REGRESSION_THRESHOLD == pytest.approx(0.15)

    def test_warning_threshold_is_7_percent(self):
        assert WARNING_THRESHOLD == pytest.approx(0.07)


# ---------------------------------------------------------------------------
# QualityBaseline dataclass
# ---------------------------------------------------------------------------

class TestQualityBaseline:
    def test_fields_accessible(self):
        b = QualityBaseline(
            model_id="gpt-4", version="2024-01",
            mean_score=85.0, std_dev=5.0, sample_count=20,
        )
        assert b.model_id == "gpt-4"
        assert b.version == "2024-01"
        assert b.mean_score == pytest.approx(85.0)
        assert b.sample_count == 20


# ---------------------------------------------------------------------------
# RegressionAlert dataclass
# ---------------------------------------------------------------------------

class TestRegressionAlert:
    def test_fields_accessible(self):
        a = RegressionAlert(
            model_id="gpt-4",
            baseline_version="2024-01",
            current_version="2024-02",
            baseline_mean=85.0,
            current_mean=70.0,
            drop_fraction=0.176,
            sample_count=10,
            severity="REGRESSION_DETECTED",
        )
        assert a.severity == "REGRESSION_DETECTED"
        assert a.drop_fraction == pytest.approx(0.176)


# ---------------------------------------------------------------------------
# RegressionDetector.record / get_version_history / get_known_models
# ---------------------------------------------------------------------------

class TestRecord:
    def test_record_single_score(self):
        d = _detector()
        d.record("gpt-4", "v1", 80.0)
        assert "gpt-4" in d.get_known_models()

    def test_version_order_preserved(self):
        d = _detector()
        d.record("gpt-4", "v1", 80.0)
        d.record("gpt-4", "v2", 75.0)
        d.record("gpt-4", "v1", 82.0)  # re-add v1 scores
        assert d.get_version_history("gpt-4") == ["v1", "v2"]

    def test_multiple_models_independent(self):
        d = _detector()
        d.record("gpt-4", "v1", 80.0)
        d.record("gpt-3.5", "v1", 70.0)
        assert set(d.get_known_models()) == {"gpt-4", "gpt-3.5"}

    def test_unknown_model_returns_empty_history(self):
        d = _detector()
        assert d.get_version_history("unknown") == []


# ---------------------------------------------------------------------------
# RegressionDetector.get_baseline
# ---------------------------------------------------------------------------

class TestGetBaseline:
    def test_baseline_none_before_any_records(self):
        d = _detector()
        assert d.get_baseline("gpt-4", "v1") is None

    def test_baseline_computes_mean(self):
        d = _detector()
        d.record("gpt-4", "v1", 80.0)
        d.record("gpt-4", "v1", 90.0)
        b = d.get_baseline("gpt-4", "v1")
        assert b.mean_score == pytest.approx(85.0)

    def test_baseline_computes_sample_count(self):
        d = _detector()
        for _ in range(5):
            d.record("gpt-4", "v1", 80.0)
        assert d.get_baseline("gpt-4", "v1").sample_count == 5

    def test_baseline_std_dev_zero_for_single_score(self):
        d = _detector()
        d.record("gpt-4", "v1", 80.0)
        assert d.get_baseline("gpt-4", "v1").std_dev == pytest.approx(0.0)

    def test_baseline_std_dev_nonzero_for_varying_scores(self):
        d = _detector()
        d.record("gpt-4", "v1", 60.0)
        d.record("gpt-4", "v1", 100.0)
        assert d.get_baseline("gpt-4", "v1").std_dev > 0.0


# ---------------------------------------------------------------------------
# RegressionDetector.detect_regression
# ---------------------------------------------------------------------------

class TestDetectRegression:
    def test_no_regression_when_quality_stable(self):
        d = _detector()
        for _ in range(5):
            d.record("gpt-4", "v1", 85.0)
        for _ in range(5):
            d.record("gpt-4", "v2", 84.0)
        assert d.detect_regression("gpt-4", "v1", "v2") is None

    def test_regression_detected_on_large_drop(self):
        d = _detector()
        for _ in range(10):
            d.record("gpt-4", "v1", 80.0)
        for _ in range(5):
            d.record("gpt-4", "v2", 60.0)   # 25% drop
        alert = d.detect_regression("gpt-4", "v1", "v2")
        assert alert is not None
        assert alert.severity == "REGRESSION_DETECTED"

    def test_warning_on_moderate_drop(self):
        d = _detector()
        for _ in range(10):
            d.record("gpt-4", "v1", 80.0)
        for _ in range(5):
            d.record("gpt-4", "v2", 73.0)   # ~8.75% drop
        alert = d.detect_regression("gpt-4", "v1", "v2")
        assert alert is not None
        assert alert.severity == "WARNING"

    def test_alert_contains_correct_versions(self):
        d = _detector()
        for _ in range(5):
            d.record("m1", "2024-01", 80.0)
        for _ in range(5):
            d.record("m1", "2024-02", 60.0)
        alert = d.detect_regression("m1", "2024-01", "2024-02")
        assert alert.baseline_version == "2024-01"
        assert alert.current_version == "2024-02"

    def test_alert_drop_fraction_correct(self):
        d = _detector()
        for _ in range(5):
            d.record("m1", "v1", 80.0)
        for _ in range(5):
            d.record("m1", "v2", 64.0)   # 20% drop
        alert = d.detect_regression("m1", "v1", "v2")
        assert alert.drop_fraction == pytest.approx(0.20)

    def test_none_when_baseline_missing(self):
        d = _detector()
        d.record("gpt-4", "v2", 70.0)
        assert d.detect_regression("gpt-4", "v1", "v2") is None

    def test_none_when_current_version_missing(self):
        d = _detector()
        for _ in range(5):
            d.record("gpt-4", "v1", 80.0)
        assert d.detect_regression("gpt-4", "v1", "v2") is None

    def test_window_limits_samples_used(self):
        d = _detector(window=3)
        for _ in range(10):
            d.record("m1", "v1", 80.0)
        # First 3 scores fine, rest terrible — window=3 should not catch the regression
        for _ in range(3):
            d.record("m1", "v2", 78.0)   # within threshold
        for _ in range(10):
            d.record("m1", "v2", 10.0)   # terrible — outside window
        alert = d.detect_regression("m1", "v1", "v2")
        # first 3 of v2 are fine → no alert
        assert alert is None

    def test_sample_count_in_alert(self):
        d = _detector(window=5)
        for _ in range(10):
            d.record("m1", "v1", 80.0)
        for _ in range(3):  # fewer than window
            d.record("m1", "v2", 50.0)
        alert = d.detect_regression("m1", "v1", "v2")
        assert alert.sample_count == 3


# ---------------------------------------------------------------------------
# RegressionDetector.check_all
# ---------------------------------------------------------------------------

class TestCheckAll:
    def test_empty_returns_empty(self):
        assert _detector().check_all() == []

    def test_finds_regression_across_consecutive_versions(self):
        d = _detector()
        for _ in range(10):
            d.record("m1", "v1", 80.0)
        for _ in range(5):
            d.record("m1", "v2", 55.0)  # 31% drop
        alerts = d.check_all()
        assert len(alerts) == 1
        assert alerts[0].model_id == "m1"

    def test_checks_all_models(self):
        d = _detector()
        for _ in range(5):
            d.record("m1", "v1", 80.0)
        for _ in range(5):
            d.record("m1", "v2", 55.0)
        for _ in range(5):
            d.record("m2", "v1", 90.0)
        for _ in range(5):
            d.record("m2", "v2", 60.0)
        alerts = d.check_all()
        model_ids = {a.model_id for a in alerts}
        assert "m1" in model_ids
        assert "m2" in model_ids

    def test_no_alert_when_quality_improves(self):
        d = _detector()
        for _ in range(5):
            d.record("m1", "v1", 70.0)
        for _ in range(5):
            d.record("m1", "v2", 90.0)  # quality improved
        assert d.check_all() == []


# ---------------------------------------------------------------------------
# RegressionDetector.detect_cusum
# ---------------------------------------------------------------------------

class TestDetectCusum:
    def test_none_for_empty_sequence(self):
        assert RegressionDetector.detect_cusum([], 80.0) is None

    def test_none_for_stable_sequence(self):
        scores = [80.0] * 20
        assert RegressionDetector.detect_cusum(scores, 80.0, threshold=5.0) is None

    def test_detects_sudden_drop(self):
        scores = [80.0] * 10 + [40.0] * 10
        idx = RegressionDetector.detect_cusum(scores, 80.0, threshold=5.0)
        assert idx is not None
        assert idx >= 10  # change detected after the drop begins

    def test_returns_int_index(self):
        scores = [80.0] * 5 + [30.0] * 5
        idx = RegressionDetector.detect_cusum(scores, 80.0, threshold=5.0)
        assert isinstance(idx, int)

    def test_none_when_baseline_mean_zero(self):
        assert RegressionDetector.detect_cusum([50.0, 60.0], 0.0) is None

    def test_higher_threshold_requires_larger_drop(self):
        scores = [80.0] * 5 + [70.0] * 5   # 12.5% drop
        idx_low = RegressionDetector.detect_cusum(scores, 80.0, threshold=1.0)
        idx_high = RegressionDetector.detect_cusum(scores, 80.0, threshold=100.0)
        # Low threshold fires; high threshold does not
        assert idx_low is not None
        assert idx_high is None


# ---------------------------------------------------------------------------
# RegressionDetector.generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_report_contains_model_id(self):
        d = _detector()
        d.record("m1", "v1", 80.0)
        report = d.generate_report("m1")
        assert report["model_id"] == "m1"

    def test_report_versions_listed(self):
        d = _detector()
        d.record("m1", "v1", 80.0)
        d.record("m1", "v2", 75.0)
        report = d.generate_report("m1")
        assert "v1" in report["versions"]
        assert "v2" in report["versions"]

    def test_report_alerts_present_on_regression(self):
        d = _detector()
        for _ in range(5):
            d.record("m1", "v1", 80.0)
        for _ in range(5):
            d.record("m1", "v2", 55.0)
        report = d.generate_report("m1")
        assert len(report["alerts"]) == 1
        assert report["alerts"][0]["severity"] == "REGRESSION_DETECTED"

    def test_report_empty_alerts_when_stable(self):
        d = _detector()
        d.record("m1", "v1", 80.0)
        assert d.generate_report("m1")["alerts"] == []


# ---------------------------------------------------------------------------
# PerformanceAggregator: quality_by_version extraction
# ---------------------------------------------------------------------------

class TestQualityByVersionExtraction:
    def test_quality_scores_grouped_by_version(self):
        agg = _agg_with_events([
            {"success": True, "quality_score": 80, "model_version": "v1"},
            {"success": True, "quality_score": 70, "model_version": "v2"},
        ])
        m = agg.get_agent_metrics("m1")
        assert "v1" in m.quality_by_version
        assert "v2" in m.quality_by_version

    def test_multiple_scores_same_version(self):
        agg = _agg_with_events([
            {"success": True, "quality_score": 80, "model_version": "v1"},
            {"success": True, "quality_score": 85, "model_version": "v1"},
        ])
        m = agg.get_agent_metrics("m1")
        assert len(m.quality_by_version["v1"]) == 2

    def test_no_version_not_tracked(self):
        agg = _agg_with_events([
            {"success": True, "quality_score": 80},  # no model_version
        ])
        m = agg.get_agent_metrics("m1")
        assert m.quality_by_version == {}

    def test_no_quality_score_not_tracked(self):
        agg = _agg_with_events([
            {"success": True, "model_version": "v1"},  # no quality_score
        ])
        m = agg.get_agent_metrics("m1")
        assert m.quality_by_version == {}


# ---------------------------------------------------------------------------
# PerformanceAggregator.get_regression_alerts
# ---------------------------------------------------------------------------

class TestGetRegressionAlerts:
    def _make_metrics(self, qbv: dict[str, list[float]]) -> AgentPerformanceMetrics:
        m = AgentPerformanceMetrics(agent_ref="m1")
        m.total_tasks = sum(len(v) for v in qbv.values())
        m.successful_tasks = m.total_tasks
        m.quality_by_version = qbv
        return m

    def test_returns_list(self):
        m = self._make_metrics({"v1": [80.0] * 5, "v2": [60.0] * 5})
        agg = _agg_with_cache({"m1": m})
        result = agg.get_regression_alerts()
        assert isinstance(result, list)

    def test_detects_regression_from_version_data(self):
        m = self._make_metrics({"v1": [80.0] * 10, "v2": [55.0] * 5})
        agg = _agg_with_cache({"m1": m})
        alerts = agg.get_regression_alerts()
        assert len(alerts) == 1

    def test_empty_when_no_version_data(self):
        m = self._make_metrics({})
        agg = _agg_with_cache({"m1": m})
        assert agg.get_regression_alerts() == []

    def test_agent_refs_filter_applies(self):
        m1 = self._make_metrics({"v1": [80.0] * 5, "v2": [55.0] * 5})
        m2 = self._make_metrics({"v1": [80.0] * 5, "v2": [55.0] * 5})
        agg = _agg_with_cache({"m1": m1, "m2": m2})
        alerts = agg.get_regression_alerts(agent_refs=["m1"])
        assert all(a.model_id == "m1" for a in alerts)


# ---------------------------------------------------------------------------
# extract_model_version utility
# ---------------------------------------------------------------------------

class TestExtractModelVersion:
    def test_none_for_none_input(self):
        assert extract_model_version(None) is None

    def test_none_for_empty_dict(self):
        assert extract_model_version({}) is None

    def test_extracts_x_model_version(self):
        headers = {"x-model-version": "gpt-4-2024-11"}
        assert extract_model_version(headers) == "gpt-4-2024-11"

    def test_extracts_x_openrouter_model(self):
        headers = {"x-openrouter-model": "mistral-7b-v0.2"}
        assert extract_model_version(headers) == "mistral-7b-v0.2"

    def test_extracts_openai_model(self):
        headers = {"openai-model": "gpt-4o-2024-05-13"}
        assert extract_model_version(headers) == "gpt-4o-2024-05-13"

    def test_priority_x_model_version_over_others(self):
        headers = {
            "x-model-version": "primary",
            "openai-model": "secondary",
        }
        assert extract_model_version(headers) == "primary"

    def test_case_insensitive_lookup(self):
        headers = {"X-Model-Version": "gpt-4-turbo"}
        assert extract_model_version(headers) == "gpt-4-turbo"

    def test_returns_none_for_unknown_headers(self):
        headers = {"content-type": "application/json", "x-request-id": "abc"}
        assert extract_model_version(headers) is None
