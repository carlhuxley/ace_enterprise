"""Tests for ModelProfile and profile-aware routing (ace_enterprise-4l4)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.broker.adaptive_broker import AdaptiveBroker, BrokerConfig
from src.broker.performance_aggregator import (
    AgentPerformanceMetrics,
    ModelProfile,
    PerformanceAggregator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _metrics(
    agent_ref="model-a",
    total=20,
    successful=16,
    task_types: dict[str, float] | None = None,
    complexities: dict[int, float] | None = None,
) -> AgentPerformanceMetrics:
    m = AgentPerformanceMetrics(agent_ref=agent_ref)
    m.total_tasks = total
    m.successful_tasks = successful
    m.failed_tasks = total - successful
    m.success_by_task_type = task_types or {}
    m.success_by_complexity = complexities or {}
    return m


def _aggregator_with(metrics_map: dict[str, AgentPerformanceMetrics]) -> PerformanceAggregator:
    """Return a PerformanceAggregator whose get_all_agent_metrics returns metrics_map."""
    agg = MagicMock(spec=PerformanceAggregator)
    agg.get_all_agent_metrics.return_value = metrics_map
    for ref, m in metrics_map.items():
        agg.get_agent_metrics.return_value = m  # last one wins; override per test if needed

    # Wire build_model_profile and get_all_model_profiles to real implementations
    real_agg = PerformanceAggregator.__new__(PerformanceAggregator)
    agg.build_model_profile.side_effect = real_agg.build_model_profile.__func__.__get__(
        agg, type(agg)
    )
    agg.get_all_model_profiles.side_effect = lambda: {
        ref: real_agg.build_model_profile(real_agg, ref, m)
        for ref, m in metrics_map.items()
    }
    return agg


# ---------------------------------------------------------------------------
# ModelProfile dataclass
# ---------------------------------------------------------------------------

class TestModelProfileDataclass:
    def test_fields_accessible(self):
        p = ModelProfile(
            model_id="m1",
            strengths=["python"],
            weaknesses=["go"],
            optimal_complexity=2,
            avoid_complexity=5,
        )
        assert p.model_id == "m1"
        assert p.strengths == ["python"]
        assert p.weaknesses == ["go"]
        assert p.optimal_complexity == 2
        assert p.avoid_complexity == 5

    def test_empty_profile(self):
        p = ModelProfile(
            model_id="m1",
            strengths=[],
            weaknesses=[],
            optimal_complexity=None,
            avoid_complexity=None,
        )
        assert p.strengths == []
        assert p.optimal_complexity is None


# ---------------------------------------------------------------------------
# PerformanceAggregator.build_model_profile
# ---------------------------------------------------------------------------

class TestBuildModelProfile:
    def setup_method(self):
        store = MagicMock()
        store.query.return_value = MagicMock(events=[])
        self.agg = PerformanceAggregator(store)

    def test_no_task_types_gives_empty_strengths_weaknesses(self):
        m = _metrics(task_types={})
        profile = self.agg.build_model_profile("m1", m)
        assert profile.strengths == []
        assert profile.weaknesses == []

    def test_single_task_type_neither_strength_nor_weakness(self):
        m = _metrics(task_types={"python": 0.9})
        profile = self.agg.build_model_profile("m1", m)
        assert profile.strengths == []
        assert profile.weaknesses == []

    def test_strength_when_rate_exceeds_avg_by_more_than_10pp(self):
        # avg = (0.9 + 0.5) / 2 = 0.7; python 0.9 > 0.7 + 0.1 = 0.8 → strength
        m = _metrics(task_types={"python": 0.9, "sql": 0.5})
        profile = self.agg.build_model_profile("m1", m)
        assert "python" in profile.strengths

    def test_weakness_when_rate_below_avg_by_more_than_10pp(self):
        # avg = 0.7; sql 0.5 < 0.7 - 0.1 = 0.6 → weakness
        m = _metrics(task_types={"python": 0.9, "sql": 0.5})
        profile = self.agg.build_model_profile("m1", m)
        assert "sql" in profile.weaknesses

    def test_within_10pp_of_avg_not_strength_or_weakness(self):
        # avg = (0.75 + 0.65) / 2 = 0.70; both within ±0.10
        m = _metrics(task_types={"python": 0.75, "sql": 0.65})
        profile = self.agg.build_model_profile("m1", m)
        assert profile.strengths == []
        assert profile.weaknesses == []

    def test_just_below_10pp_above_avg_not_strength(self):
        # avg = (0.79 + 0.61) / 2 = 0.70; python 0.79 = avg + 0.09 → not strength (needs >0.10)
        m = _metrics(task_types={"python": 0.79, "sql": 0.61})
        profile = self.agg.build_model_profile("m1", m)
        assert "python" not in profile.strengths

    def test_optimal_complexity_is_best_performing_level(self):
        m = _metrics(complexities={1: 0.6, 2: 0.9, 3: 0.5})
        profile = self.agg.build_model_profile("m1", m)
        assert profile.optimal_complexity == 2

    def test_avoid_complexity_is_worst_performing_level(self):
        m = _metrics(complexities={1: 0.6, 2: 0.9, 3: 0.5})
        profile = self.agg.build_model_profile("m1", m)
        assert profile.avoid_complexity == 3

    def test_no_complexity_data_gives_none(self):
        m = _metrics(complexities={})
        profile = self.agg.build_model_profile("m1", m)
        assert profile.optimal_complexity is None
        assert profile.avoid_complexity is None

    def test_model_id_matches_agent_ref(self):
        m = _metrics()
        profile = self.agg.build_model_profile("my-model", m)
        assert profile.model_id == "my-model"

    def test_multiple_strengths_detected(self):
        # avg = (0.95 + 0.4 + 0.4) / 3 = 0.583; python 0.95 > 0.683 → strength
        m = _metrics(task_types={"python": 0.95, "sql": 0.40, "bash": 0.40})
        profile = self.agg.build_model_profile("m1", m)
        assert "python" in profile.strengths

    def test_multiple_weaknesses_detected(self):
        # avg ≈ 0.583; sql 0.40 and bash 0.40 < 0.483 → both weaknesses
        m = _metrics(task_types={"python": 0.95, "sql": 0.40, "bash": 0.40})
        profile = self.agg.build_model_profile("m1", m)
        assert "sql" in profile.weaknesses
        assert "bash" in profile.weaknesses


# ---------------------------------------------------------------------------
# PerformanceAggregator.get_model_profile / get_all_model_profiles
# ---------------------------------------------------------------------------

class TestGetModelProfiles:
    def _make_agg(self, task_types: dict[str, float]) -> PerformanceAggregator:
        store = MagicMock()
        m = _metrics("m1", task_types=task_types)
        store.query.return_value = MagicMock(events=[])
        agg = PerformanceAggregator(store)
        # Inject pre-built metrics into cache
        agg._cache["m1"] = m
        from datetime import datetime, timedelta
        agg._cache_expiry = datetime.now() + timedelta(minutes=5)
        return agg

    def test_get_model_profile_returns_model_profile(self):
        agg = self._make_agg({"python": 0.9, "sql": 0.5})
        profile = agg.get_model_profile("m1")
        assert isinstance(profile, ModelProfile)

    def test_get_model_profile_model_id_correct(self):
        agg = self._make_agg({"python": 0.9, "sql": 0.5})
        profile = agg.get_model_profile("m1")
        assert profile.model_id == "m1"

    def test_get_all_model_profiles_returns_dict(self):
        store = MagicMock()
        ma = _metrics("m1", task_types={"python": 0.9})
        mb = _metrics("m2", task_types={"go": 0.8})
        store.query.return_value = MagicMock(events=[])
        agg = PerformanceAggregator(store)
        agg._cache = {"m1": ma, "m2": mb}
        from datetime import datetime, timedelta
        agg._cache_expiry = datetime.now() + timedelta(minutes=5)

        profiles = agg.get_all_model_profiles()
        assert set(profiles.keys()) == {"m1", "m2"}
        assert all(isinstance(p, ModelProfile) for p in profiles.values())

    def test_get_all_model_profiles_empty_when_no_agents(self):
        store = MagicMock()
        store.query.return_value = MagicMock(events=[])
        agg = PerformanceAggregator(store)
        agg._cache = {}
        from datetime import datetime, timedelta
        agg._cache_expiry = datetime.now() + timedelta(minutes=5)
        assert agg.get_all_model_profiles() == {}


# ---------------------------------------------------------------------------
# AdaptiveBroker profile-aware scoring
# ---------------------------------------------------------------------------

class TestAdaptiveBrokerProfileScoring:
    def _make_broker(self, metrics_map):
        store = MagicMock()
        store.query.return_value = MagicMock(events=[])
        agg = PerformanceAggregator(store)

        from datetime import datetime, timedelta
        agg._cache = metrics_map
        agg._cache_expiry = datetime.now() + timedelta(minutes=5)

        return AdaptiveBroker(agg)

    def test_strength_domain_boosts_score(self):
        # m1: python strength, m2: average everywhere
        m1 = _metrics("m1", total=20, successful=16,
                      task_types={"python": 0.95, "sql": 0.45})
        m2 = _metrics("m2", total=20, successful=16,
                      task_types={"python": 0.70, "sql": 0.70})
        broker = self._make_broker({"m1": m1, "m2": m2})
        result = broker.route_task(task_type="python")
        # m1 has python as strength → should outscore m2 for python tasks
        assert result.selected_agent == "m1"

    def test_weakness_domain_penalises_score(self):
        # m1: python is a weakness, m2: average python
        m1 = _metrics("m1", total=20, successful=16,
                      task_types={"python": 0.40, "sql": 0.90})
        m2 = _metrics("m2", total=20, successful=16,
                      task_types={"python": 0.70, "sql": 0.70})
        broker = self._make_broker({"m1": m1, "m2": m2})
        result = broker.route_task(task_type="python")
        # m1 has python as weakness → m2 preferred
        assert result.selected_agent == "m2"

    def test_no_task_type_routing_unaffected_by_profile(self):
        m1 = _metrics("m1", total=30, successful=27)  # 90% overall
        m2 = _metrics("m2", total=30, successful=15)  # 50% overall
        broker = self._make_broker({"m1": m1, "m2": m2})
        result = broker.route_task()
        assert result.selected_agent == "m1"

    def test_calculate_score_strength_gives_boost(self):
        store = MagicMock()
        store.query.return_value = MagicMock(events=[])
        agg = PerformanceAggregator(store)
        broker = AdaptiveBroker(agg)

        m = _metrics(total=20, successful=16)
        m.success_by_task_type = {"python": 0.9}

        profile_with = ModelProfile(
            model_id="m", strengths=["python"], weaknesses=[],
            optimal_complexity=None, avoid_complexity=None,
        )
        profile_without = ModelProfile(
            model_id="m", strengths=[], weaknesses=[],
            optimal_complexity=None, avoid_complexity=None,
        )

        score_with = broker._calculate_score(m, "python", None, profile_with)
        score_without = broker._calculate_score(m, "python", None, profile_without)
        assert score_with > score_without

    def test_calculate_score_weakness_gives_penalty(self):
        store = MagicMock()
        store.query.return_value = MagicMock(events=[])
        agg = PerformanceAggregator(store)
        broker = AdaptiveBroker(agg)

        m = _metrics(total=20, successful=16)
        m.success_by_task_type = {"go": 0.5}

        profile_weak = ModelProfile(
            model_id="m", strengths=[], weaknesses=["go"],
            optimal_complexity=None, avoid_complexity=None,
        )
        profile_neutral = ModelProfile(
            model_id="m", strengths=[], weaknesses=[],
            optimal_complexity=None, avoid_complexity=None,
        )

        score_weak = broker._calculate_score(m, "go", None, profile_weak)
        score_neutral = broker._calculate_score(m, "go", None, profile_neutral)
        assert score_weak < score_neutral

    def test_calculate_score_no_profile_unchanged(self):
        store = MagicMock()
        store.query.return_value = MagicMock(events=[])
        agg = PerformanceAggregator(store)
        broker = AdaptiveBroker(agg)

        m = _metrics(total=20, successful=16)
        score_with_none = broker._calculate_score(m, "python", None, None)
        score_with_neutral = broker._calculate_score(
            m, "python", None,
            ModelProfile("m", [], [], None, None),
        )
        assert score_with_none == pytest.approx(score_with_neutral)

    def test_score_clamped_to_one_with_boost(self):
        store = MagicMock()
        store.query.return_value = MagicMock(events=[])
        agg = PerformanceAggregator(store)
        broker = AdaptiveBroker(agg)

        m = _metrics(total=100, successful=100)  # 100% success
        profile = ModelProfile("m", strengths=["python"], weaknesses=[], optimal_complexity=None, avoid_complexity=None)
        score = broker._calculate_score(m, "python", None, profile)
        assert score <= 1.0
