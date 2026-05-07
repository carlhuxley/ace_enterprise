import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from src.reliability.tdd_cycle_analyzer import TDDCycleAnalyzer, CyclePeriod
from src.reliability.playbook_analyzer import PlaybookReliabilityAnalyzer, BulletReliability


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_logger(records):
    logger = MagicMock()
    logger.get_tdd_cycle_records.return_value = records
    return logger


def _cycle(result="SUCCESS", retry_count=0, bullet_ids=None, days_ago=1):
    return {
        "timestamp": datetime.utcnow() - timedelta(days=days_ago),
        "result": result,
        "retry_count": retry_count,
        "playbook_id": "pb1",
        "retrieved_bullet_ids": bullet_ids or [],
        "learned_bullet_count": 0,
    }


# ---------------------------------------------------------------------------
# TDDCycleAnalyzer.first_pass_rate
# ---------------------------------------------------------------------------

def test_first_pass_rate_zero_when_no_records():
    analyzer = TDDCycleAnalyzer(_make_logger([]))
    assert analyzer.first_pass_rate() == 0.0


def test_first_pass_rate_counts_success_with_zero_retries():
    records = [_cycle("SUCCESS", 0), _cycle("SUCCESS", 0), _cycle("FAILED", 0)]
    analyzer = TDDCycleAnalyzer(_make_logger(records))
    assert analyzer.first_pass_rate() == pytest.approx(2 / 3)


def test_first_pass_rate_excludes_success_with_retries():
    records = [_cycle("SUCCESS", 2), _cycle("SUCCESS", 0)]
    analyzer = TDDCycleAnalyzer(_make_logger(records))
    assert analyzer.first_pass_rate() == pytest.approx(0.5)


def test_first_pass_rate_failed_cycle_with_zero_retries_not_counted():
    records = [_cycle("FAILED", 0), _cycle("FAILED", 0)]
    analyzer = TDDCycleAnalyzer(_make_logger(records))
    assert analyzer.first_pass_rate() == 0.0


def test_first_pass_rate_passes_playbook_id_to_logger():
    logger = _make_logger([])
    analyzer = TDDCycleAnalyzer(logger)
    analyzer.first_pass_rate(playbook_id="pb_x")
    logger.get_tdd_cycle_records.assert_called_once_with(playbook_id="pb_x", since=None)


# ---------------------------------------------------------------------------
# TDDCycleAnalyzer.trend
# ---------------------------------------------------------------------------

def test_trend_empty_when_no_records():
    analyzer = TDDCycleAnalyzer(_make_logger([]))
    assert analyzer.trend() == []


def test_trend_omits_empty_periods():
    # One record 3 days ago — only one period should appear in a 7-day window
    records = [_cycle("SUCCESS", 0, days_ago=3)]
    analyzer = TDDCycleAnalyzer(_make_logger(records))
    result = analyzer.trend(periods=10, period_days=7)
    assert len(result) == 1


def test_trend_periods_ordered_oldest_first():
    records = [
        _cycle("SUCCESS", 0, days_ago=3),
        _cycle("FAILED", 0, days_ago=10),
    ]
    analyzer = TDDCycleAnalyzer(_make_logger(records))
    result = analyzer.trend(periods=4, period_days=7)
    assert len(result) == 2
    assert result[0].period_start < result[1].period_start


def test_trend_first_pass_rate_correct_per_period():
    now = datetime.utcnow()
    records = [
        {**_cycle("SUCCESS", 0, days_ago=2), "timestamp": now - timedelta(days=2)},
        {**_cycle("FAILED",  0, days_ago=3), "timestamp": now - timedelta(days=3)},
    ]
    analyzer = TDDCycleAnalyzer(_make_logger(records))
    result = analyzer.trend(periods=1, period_days=7)
    assert len(result) == 1
    assert result[0].total_cycles == 2
    assert result[0].first_pass_count == 1
    assert result[0].first_pass_rate == pytest.approx(0.5)


def test_trend_returns_cycle_period_dataclass():
    records = [_cycle("SUCCESS", 0, days_ago=1)]
    analyzer = TDDCycleAnalyzer(_make_logger(records))
    result = analyzer.trend(periods=1, period_days=7)
    assert isinstance(result[0], CyclePeriod)


# ---------------------------------------------------------------------------
# PlaybookReliabilityAnalyzer.bullet_reliability
# ---------------------------------------------------------------------------

def test_bullet_reliability_empty_when_no_records():
    analyzer = PlaybookReliabilityAnalyzer(_make_logger([]), MagicMock())
    assert analyzer.bullet_reliability("pb1") == []


def test_bullet_reliability_excludes_unretrieved_bullets():
    records = [_cycle("SUCCESS", 0, bullet_ids=["b1"])]
    analyzer = PlaybookReliabilityAnalyzer(_make_logger(records), MagicMock())
    result = analyzer.bullet_reliability("pb1")
    ids = [r.bullet_id for r in result]
    assert "b1" in ids
    assert len(result) == 1


def test_bullet_reliability_first_pass_rate_correct():
    records = [
        _cycle("SUCCESS", 0, bullet_ids=["b1"]),
        _cycle("SUCCESS", 1, bullet_ids=["b1"]),  # retry — not first pass
        _cycle("FAILED",  0, bullet_ids=["b1"]),
    ]
    analyzer = PlaybookReliabilityAnalyzer(_make_logger(records), MagicMock())
    result = analyzer.bullet_reliability("pb1")
    assert len(result) == 1
    b = result[0]
    assert b.bullet_id == "b1"
    assert b.times_retrieved == 3
    assert b.first_pass_count == 1
    assert b.first_pass_rate == pytest.approx(1 / 3)


def test_bullet_reliability_sorted_by_first_pass_rate_descending():
    records = [
        _cycle("SUCCESS", 0, bullet_ids=["good"]),
        _cycle("SUCCESS", 0, bullet_ids=["good"]),
        _cycle("FAILED",  0, bullet_ids=["bad"]),
        _cycle("FAILED",  0, bullet_ids=["bad"]),
    ]
    analyzer = PlaybookReliabilityAnalyzer(_make_logger(records), MagicMock())
    result = analyzer.bullet_reliability("pb1")
    assert result[0].bullet_id == "good"
    assert result[-1].bullet_id == "bad"


def test_bullet_reliability_multiple_bullets_per_cycle():
    records = [_cycle("SUCCESS", 0, bullet_ids=["b1", "b2", "b3"])]
    analyzer = PlaybookReliabilityAnalyzer(_make_logger(records), MagicMock())
    result = analyzer.bullet_reliability("pb1")
    assert len(result) == 3
    assert all(r.first_pass_rate == 1.0 for r in result)


def test_bullet_reliability_returns_dataclass():
    records = [_cycle("SUCCESS", 0, bullet_ids=["b1"])]
    analyzer = PlaybookReliabilityAnalyzer(_make_logger(records), MagicMock())
    result = analyzer.bullet_reliability("pb1")
    assert isinstance(result[0], BulletReliability)
