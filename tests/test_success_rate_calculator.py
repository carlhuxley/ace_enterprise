import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from src.analytics.success_rate_calculator import (
    SuccessRateCalculator,
    RatePeriod,
    VersionRate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_logger(records):
    logger = MagicMock()
    logger.get_experiment_records.return_value = records
    return logger


def _record(result="SUCCESS", experiment_type="tdd_cycle", version="v1", days_ago=1):
    return {
        "timestamp": datetime.utcnow() - timedelta(days=days_ago),
        "result": result,
        "playbook_version": version,
        "experiment_type": experiment_type,
    }


# ---------------------------------------------------------------------------
# overall_rate
# ---------------------------------------------------------------------------

def test_overall_rate_zero_when_no_records():
    calc = SuccessRateCalculator(_make_logger([]))
    assert calc.overall_rate() == 0.0


def test_overall_rate_counts_success_fraction():
    records = [_record("SUCCESS"), _record("SUCCESS"), _record("FAILED")]
    calc = SuccessRateCalculator(_make_logger(records))
    assert calc.overall_rate() == pytest.approx(2 / 3)


def test_overall_rate_timeout_and_error_not_counted_as_success():
    records = [_record("TIMEOUT"), _record("ERROR"), _record("SUCCESS")]
    calc = SuccessRateCalculator(_make_logger(records))
    assert calc.overall_rate() == pytest.approx(1 / 3)


def test_overall_rate_passes_experiment_type_to_logger():
    logger = _make_logger([])
    calc = SuccessRateCalculator(logger)
    calc.overall_rate(experiment_type="ml_experiment")
    logger.get_experiment_records.assert_called_once_with(
        experiment_type="ml_experiment", since=None
    )


def test_overall_rate_passes_since_to_logger():
    logger = _make_logger([])
    calc = SuccessRateCalculator(logger)
    cutoff = datetime(2026, 1, 1)
    calc.overall_rate(since=cutoff)
    logger.get_experiment_records.assert_called_once_with(
        experiment_type=None, since=cutoff
    )


# ---------------------------------------------------------------------------
# rate_by_type
# ---------------------------------------------------------------------------

def test_rate_by_type_returns_dict_of_rates():
    records = [
        _record("SUCCESS", experiment_type="tdd_cycle"),
        _record("FAILED",  experiment_type="tdd_cycle"),
        _record("SUCCESS", experiment_type="ml_experiment"),
    ]
    calc = SuccessRateCalculator(_make_logger(records))
    rates = calc.rate_by_type()
    assert rates["tdd_cycle"] == pytest.approx(0.5)
    assert rates["ml_experiment"] == pytest.approx(1.0)


def test_rate_by_type_only_includes_types_present_in_records():
    records = [_record("SUCCESS", experiment_type="tdd_cycle")]
    calc = SuccessRateCalculator(_make_logger(records))
    rates = calc.rate_by_type()
    assert set(rates.keys()) == {"tdd_cycle"}


def test_rate_by_type_passes_since_to_logger():
    logger = _make_logger([])
    calc = SuccessRateCalculator(logger)
    cutoff = datetime(2026, 1, 1)
    calc.rate_by_type(since=cutoff)
    logger.get_experiment_records.assert_called_once_with(since=cutoff)


# ---------------------------------------------------------------------------
# rate_by_playbook_version
# ---------------------------------------------------------------------------

def test_rate_by_playbook_version_computes_per_version_rate():
    records = [
        _record("SUCCESS", version="v1"),
        _record("FAILED",  version="v1"),
        _record("SUCCESS", version="v2"),
        _record("SUCCESS", version="v2"),
    ]
    calc = SuccessRateCalculator(_make_logger(records))
    result = calc.rate_by_playbook_version()
    by_version = {r.playbook_version: r for r in result}
    assert by_version["v1"].success_rate == pytest.approx(0.5)
    assert by_version["v2"].success_rate == pytest.approx(1.0)


def test_rate_by_playbook_version_sorted_newest_first():
    records = [
        _record("SUCCESS", version="v1"),
        _record("SUCCESS", version="v3"),
        _record("SUCCESS", version="v2"),
    ]
    calc = SuccessRateCalculator(_make_logger(records))
    result = calc.rate_by_playbook_version()
    versions = [r.playbook_version for r in result]
    assert versions == sorted(versions, reverse=True)


def test_rate_by_playbook_version_includes_total_and_success_count():
    records = [
        _record("SUCCESS", version="v1"),
        _record("SUCCESS", version="v1"),
        _record("FAILED",  version="v1"),
    ]
    calc = SuccessRateCalculator(_make_logger(records))
    result = calc.rate_by_playbook_version()
    assert len(result) == 1
    vr = result[0]
    assert vr.total == 3
    assert vr.success_count == 2


def test_rate_by_playbook_version_passes_experiment_type_to_logger():
    logger = _make_logger([])
    calc = SuccessRateCalculator(logger)
    calc.rate_by_playbook_version(experiment_type="tdd_cycle")
    logger.get_experiment_records.assert_called_once_with(experiment_type="tdd_cycle")


def test_rate_by_playbook_version_returns_version_rate_dataclass():
    records = [_record("SUCCESS", version="v1")]
    calc = SuccessRateCalculator(_make_logger(records))
    result = calc.rate_by_playbook_version()
    assert isinstance(result[0], VersionRate)


# ---------------------------------------------------------------------------
# trend
# ---------------------------------------------------------------------------

def test_trend_empty_when_no_records():
    calc = SuccessRateCalculator(_make_logger([]))
    assert calc.trend() == []


def test_trend_omits_empty_periods():
    records = [_record("SUCCESS", days_ago=3)]
    calc = SuccessRateCalculator(_make_logger(records))
    result = calc.trend(periods=10, period_days=7)
    assert len(result) == 1


def test_trend_ordered_oldest_first():
    records = [
        _record("SUCCESS", days_ago=3),
        _record("FAILED",  days_ago=10),
    ]
    calc = SuccessRateCalculator(_make_logger(records))
    result = calc.trend(periods=4, period_days=7)
    assert len(result) == 2
    assert result[0].period_start < result[1].period_start


def test_trend_correct_success_rate_per_period():
    now = datetime.utcnow()
    records = [
        {**_record("SUCCESS", days_ago=2), "timestamp": now - timedelta(days=2)},
        {**_record("FAILED",  days_ago=3), "timestamp": now - timedelta(days=3)},
    ]
    calc = SuccessRateCalculator(_make_logger(records))
    result = calc.trend(periods=1, period_days=7)
    assert len(result) == 1
    assert result[0].total == 2
    assert result[0].success_count == 1
    assert result[0].success_rate == pytest.approx(0.5)


def test_trend_returns_rate_period_dataclass():
    records = [_record("SUCCESS", days_ago=1)]
    calc = SuccessRateCalculator(_make_logger(records))
    result = calc.trend(periods=1, period_days=7)
    assert isinstance(result[0], RatePeriod)


def test_trend_passes_experiment_type_to_logger():
    logger = _make_logger([])
    calc = SuccessRateCalculator(logger)
    calc.trend(experiment_type="ml_experiment")
    _, kwargs = logger.get_experiment_records.call_args
    assert kwargs.get("experiment_type") == "ml_experiment"
