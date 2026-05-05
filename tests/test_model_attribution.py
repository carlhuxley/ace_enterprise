"""
Tests for OpenRouter Model Attribution in Performance Metrics.

Tests all scenarios from the Gherkin feature file:
1. Record model attribution in CYCLE_COMPLETED audit event
2. Aggregate performance metrics by model ID
3. Query top models by success rate
4. Filter performance by model family
5. Get best model for a specific task type
6. Track model performance over time
"""
import pytest
from datetime import datetime, timedelta

from src.benchmark.model_attribution import (
    ModelAttributionTracker,
    TaskCompletion,
    ModelMetrics,
    ModelFamilyMetrics,
    DailyMetrics,
)


class TestRecordModelAttribution:
    """Scenario: Record model attribution in CYCLE_COMPLETED audit event"""

    def test_record_completion_stores_model_attribution(self):
        """Given an agent completes a task using OpenRouter"""
        tracker = ModelAttributionTracker()

        completion = tracker.record_completion(
            model_id="qwen/qwen3-coder:free",
            requested_model="qwen/qwen3-coder:free",
            provider="openrouter",
            task_type="coding",
            success=True,
            quality_score=85.0,
        )

        assert completion.model_id == "qwen/qwen3-coder:free"
        assert completion.requested_model == "qwen/qwen3-coder:free"
        assert completion.provider == "openrouter"

    def test_to_audit_payload_contains_model_fields(self):
        """Then the audit payload should contain model_id, requested_model, provider"""
        tracker = ModelAttributionTracker()

        payload = tracker.to_audit_payload(
            model_id="qwen/qwen3-coder:free",
            requested_model="qwen/qwen3-coder:free",
            provider="openrouter",
        )

        assert payload["model_id"] == "qwen/qwen3-coder:free"
        assert payload["requested_model"] == "qwen/qwen3-coder:free"
        assert payload["provider"] == "openrouter"


class TestAggregatePerformanceByModel:
    """Scenario: Aggregate performance metrics by model ID"""

    @pytest.fixture
    def tracker_with_data(self):
        """Given the following task completions are recorded"""
        tracker = ModelAttributionTracker()

        # qwen/qwen3-coder:free - 2 successes
        tracker.record_completion(
            model_id="qwen/qwen3-coder:free",
            requested_model="qwen/qwen3-coder:free",
            provider="openrouter",
            task_type="coding",
            success=True,
            quality_score=85.0,
        )
        tracker.record_completion(
            model_id="qwen/qwen3-coder:free",
            requested_model="qwen/qwen3-coder:free",
            provider="openrouter",
            task_type="coding",
            success=True,
            quality_score=90.0,
        )

        # meta-llama/llama-3-8b - 1 success, 1 failure
        tracker.record_completion(
            model_id="meta-llama/llama-3-8b",
            requested_model="meta-llama/llama-3-8b",
            provider="openrouter",
            task_type="coding",
            success=True,
            quality_score=75.0,
        )
        tracker.record_completion(
            model_id="meta-llama/llama-3-8b",
            requested_model="meta-llama/llama-3-8b",
            provider="openrouter",
            task_type="coding",
            success=False,
            quality_score=40.0,
        )

        return tracker

    def test_qwen_success_rate(self, tracker_with_data):
        """Then model qwen/qwen3-coder:free should have success_rate 1.0"""
        metrics = tracker_with_data.get_model_metrics("qwen/qwen3-coder:free")

        assert metrics is not None
        assert metrics.success_rate == 1.0

    def test_qwen_avg_quality_score(self, tracker_with_data):
        """And model qwen/qwen3-coder:free should have avg_quality_score 87.5"""
        metrics = tracker_with_data.get_model_metrics("qwen/qwen3-coder:free")

        assert metrics is not None
        assert metrics.avg_quality_score == 87.5

    def test_llama_success_rate(self, tracker_with_data):
        """Then model meta-llama/llama-3-8b should have success_rate 0.5"""
        metrics = tracker_with_data.get_model_metrics("meta-llama/llama-3-8b")

        assert metrics is not None
        assert metrics.success_rate == 0.5

    def test_llama_avg_quality_score(self, tracker_with_data):
        """And model meta-llama/llama-3-8b should have avg_quality_score 57.5"""
        metrics = tracker_with_data.get_model_metrics("meta-llama/llama-3-8b")

        assert metrics is not None
        assert metrics.avg_quality_score == 57.5


class TestQueryTopModels:
    """Scenario: Query top models by success rate"""

    @pytest.fixture
    def tracker_with_multiple_models(self):
        """Given multiple models have recorded performance data"""
        tracker = ModelAttributionTracker()

        # Model A: 100% success rate
        for _ in range(5):
            tracker.record_completion(
                model_id="model-a/best",
                requested_model="model-a/best",
                provider="openrouter",
                task_type="coding",
                success=True,
                quality_score=90.0,
            )

        # Model B: 80% success rate
        for i in range(5):
            tracker.record_completion(
                model_id="model-b/good",
                requested_model="model-b/good",
                provider="openrouter",
                task_type="coding",
                success=(i < 4),  # 4 success, 1 failure
                quality_score=80.0,
            )

        # Model C: 60% success rate
        for i in range(5):
            tracker.record_completion(
                model_id="model-c/okay",
                requested_model="model-c/okay",
                provider="openrouter",
                task_type="coding",
                success=(i < 3),  # 3 success, 2 failures
                quality_score=70.0,
            )

        # Model D: 40% success rate
        for i in range(5):
            tracker.record_completion(
                model_id="model-d/poor",
                requested_model="model-d/poor",
                provider="openrouter",
                task_type="coding",
                success=(i < 2),  # 2 success, 3 failures
                quality_score=60.0,
            )

        return tracker

    def test_get_top_3_models(self, tracker_with_multiple_models):
        """When I request the top 3 models by success rate"""
        top_models = tracker_with_multiple_models.get_top_models(n=3)

        assert len(top_models) == 3

    def test_top_models_are_ranked(self, tracker_with_multiple_models):
        """Then I should receive a ranked list of models"""
        top_models = tracker_with_multiple_models.get_top_models(n=3)

        assert top_models[0].model_id == "model-a/best"
        assert top_models[1].model_id == "model-b/good"
        assert top_models[2].model_id == "model-c/okay"

    def test_top_models_include_required_fields(self, tracker_with_multiple_models):
        """And each entry should include model_id, success_rate, and task_count"""
        top_models = tracker_with_multiple_models.get_top_models(n=3)

        for model in top_models:
            assert hasattr(model, "model_id")
            assert hasattr(model, "success_rate")
            assert hasattr(model, "task_count")
            assert model.task_count > 0


class TestFilterByModelFamily:
    """Scenario: Filter performance by model family"""

    @pytest.fixture
    def tracker_with_families(self):
        """Given performance data exists for models"""
        tracker = ModelAttributionTracker()

        models = [
            "qwen/qwen3-coder:free",
            "qwen/qwen-2.5-72b",
            "meta-llama/llama-3-8b",
            "meta-llama/llama-3.1-70b",
        ]

        for model_id in models:
            for i in range(3):
                tracker.record_completion(
                    model_id=model_id,
                    requested_model=model_id,
                    provider="openrouter",
                    task_type="coding",
                    success=(i < 2),  # 2/3 success rate
                    quality_score=75.0 + (i * 5),
                )

        return tracker

    def test_filter_by_qwen_family(self, tracker_with_families):
        """When I filter by model family "qwen" Then I should only see qwen/ models"""
        qwen_models = tracker_with_families.filter_by_model_family("qwen")

        assert len(qwen_models) == 2
        for model in qwen_models:
            assert model.model_id.startswith("qwen/")

    def test_filter_excludes_other_families(self, tracker_with_families):
        """Filter should not include models from other families"""
        qwen_models = tracker_with_families.filter_by_model_family("qwen")

        model_ids = [m.model_id for m in qwen_models]
        assert "meta-llama/llama-3-8b" not in model_ids
        assert "meta-llama/llama-3.1-70b" not in model_ids

    def test_get_aggregated_family_stats(self, tracker_with_families):
        """And I should see aggregated stats for the qwen family"""
        family_metrics = tracker_with_families.get_family_metrics("qwen")

        assert family_metrics.family == "qwen"
        assert len(family_metrics.models) == 2
        assert family_metrics.task_count == 6  # 2 models * 3 tasks each
        assert family_metrics.success_count == 4  # 2 models * 2 successes each


class TestBestModelForTaskType:
    """Scenario: Get best model for a specific task type"""

    @pytest.fixture
    def tracker_with_task_types(self):
        """Given models have varying success rates for different task types"""
        tracker = ModelAttributionTracker()

        # qwen is better at coding (95% vs 80%)
        # Record 20 coding tasks for qwen: 19 success
        for i in range(20):
            tracker.record_completion(
                model_id="qwen/qwen3-coder:free",
                requested_model="qwen/qwen3-coder:free",
                provider="openrouter",
                task_type="coding",
                success=(i < 19),  # 19/20 = 95%
                quality_score=85.0,
            )

        # Record 10 testing tasks for qwen: 8 success
        for i in range(10):
            tracker.record_completion(
                model_id="qwen/qwen3-coder:free",
                requested_model="qwen/qwen3-coder:free",
                provider="openrouter",
                task_type="testing",
                success=(i < 8),  # 8/10 = 80%
                quality_score=75.0,
            )

        # llama is better at testing (90% vs 70%)
        # Record 10 coding tasks for llama: 7 success
        for i in range(10):
            tracker.record_completion(
                model_id="meta-llama/llama-3-8b",
                requested_model="meta-llama/llama-3-8b",
                provider="openrouter",
                task_type="coding",
                success=(i < 7),  # 7/10 = 70%
                quality_score=70.0,
            )

        # Record 10 testing tasks for llama: 9 success
        for i in range(10):
            tracker.record_completion(
                model_id="meta-llama/llama-3-8b",
                requested_model="meta-llama/llama-3-8b",
                provider="openrouter",
                task_type="testing",
                success=(i < 9),  # 9/10 = 90%
                quality_score=80.0,
            )

        return tracker

    def test_best_model_for_coding(self, tracker_with_task_types):
        """When I query the best model for task_type coding, result should be qwen"""
        best = tracker_with_task_types.get_best_model_for_task_type("coding")

        assert best == "qwen/qwen3-coder:free"

    def test_best_model_for_testing(self, tracker_with_task_types):
        """When I query the best model for task_type testing, result should be llama"""
        best = tracker_with_task_types.get_best_model_for_task_type("testing")

        assert best == "meta-llama/llama-3-8b"

    def test_model_task_type_specific_metrics(self, tracker_with_task_types):
        """Can query metrics for specific model+task_type combination"""
        metrics = tracker_with_task_types.get_model_task_type_metrics(
            "qwen/qwen3-coder:free",
            "coding",
        )

        assert metrics is not None
        assert metrics.task_count == 20
        assert metrics.success_rate == 0.95


class TestTrackPerformanceOverTime:
    """Scenario: Track model performance over time"""

    @pytest.fixture
    def tracker_with_historical_data(self):
        """Given model qwen/qwen3-coder:free has historical performance data"""
        tracker = ModelAttributionTracker()
        base_time = datetime.now()

        # Day 1-3: Lower performance (60% success)
        for day_offset in range(3):
            day = base_time - timedelta(days=6 - day_offset)
            for i in range(5):
                tracker.record_completion(
                    model_id="qwen/qwen3-coder:free",
                    requested_model="qwen/qwen3-coder:free",
                    provider="openrouter",
                    task_type="coding",
                    success=(i < 3),  # 60% success
                    quality_score=70.0,
                    timestamp=day,
                )

        # Day 4-7: Higher performance (80% success)
        for day_offset in range(4):
            day = base_time - timedelta(days=3 - day_offset)
            for i in range(5):
                tracker.record_completion(
                    model_id="qwen/qwen3-coder:free",
                    requested_model="qwen/qwen3-coder:free",
                    provider="openrouter",
                    task_type="coding",
                    success=(i < 4),  # 80% success
                    quality_score=85.0,
                    timestamp=day,
                )

        return tracker

    def test_get_daily_metrics(self, tracker_with_historical_data):
        """When I query performance for the last 7 days, I should see daily metrics"""
        daily = tracker_with_historical_data.get_daily_metrics(
            "qwen/qwen3-coder:free",
            days=7,
        )

        assert len(daily) == 7

    def test_daily_success_rates(self, tracker_with_historical_data):
        """Then I should see daily success rates"""
        daily = tracker_with_historical_data.get_daily_metrics(
            "qwen/qwen3-coder:free",
            days=7,
        )

        for day_metrics in daily:
            assert hasattr(day_metrics, "success_rate")
            assert 0.0 <= day_metrics.success_rate <= 1.0

    def test_daily_quality_scores(self, tracker_with_historical_data):
        """And I should see daily average quality scores"""
        daily = tracker_with_historical_data.get_daily_metrics(
            "qwen/qwen3-coder:free",
            days=7,
        )

        for day_metrics in daily:
            assert hasattr(day_metrics, "avg_quality_score")
            assert day_metrics.avg_quality_score > 0

    def test_detect_improving_trend(self, tracker_with_historical_data):
        """And I should be able to detect performance trends"""
        trend = tracker_with_historical_data.detect_performance_trend(
            "qwen/qwen3-coder:free",
            days=7,
        )

        # First half: 60% success, Second half: 80% success -> improving
        assert trend == "improving"

    def test_detect_declining_trend(self):
        """Test detecting a declining trend"""
        tracker = ModelAttributionTracker()
        base_time = datetime.now()

        # Day 1-3: Higher performance (80%)
        for day_offset in range(3):
            day = base_time - timedelta(days=6 - day_offset)
            for i in range(5):
                tracker.record_completion(
                    model_id="declining-model",
                    requested_model="declining-model",
                    provider="openrouter",
                    task_type="coding",
                    success=(i < 4),  # 80%
                    quality_score=80.0,
                    timestamp=day,
                )

        # Day 4-7: Lower performance (40%)
        for day_offset in range(4):
            day = base_time - timedelta(days=3 - day_offset)
            for i in range(5):
                tracker.record_completion(
                    model_id="declining-model",
                    requested_model="declining-model",
                    provider="openrouter",
                    task_type="coding",
                    success=(i < 2),  # 40%
                    quality_score=60.0,
                    timestamp=day,
                )

        trend = tracker.detect_performance_trend("declining-model", days=7)
        assert trend == "declining"

    def test_detect_stable_trend(self):
        """Test detecting a stable trend"""
        tracker = ModelAttributionTracker()
        base_time = datetime.now()

        # All days: consistent 70% success
        for day_offset in range(7):
            day = base_time - timedelta(days=6 - day_offset)
            for i in range(10):
                tracker.record_completion(
                    model_id="stable-model",
                    requested_model="stable-model",
                    provider="openrouter",
                    task_type="coding",
                    success=(i < 7),  # 70%
                    quality_score=75.0,
                    timestamp=day,
                )

        trend = tracker.detect_performance_trend("stable-model", days=7)
        assert trend == "stable"


class TestEdgeCases:
    """Edge cases and error handling"""

    def test_get_metrics_for_unknown_model(self):
        """Should return None for unknown model"""
        tracker = ModelAttributionTracker()
        metrics = tracker.get_model_metrics("unknown/model")

        assert metrics is None

    def test_best_model_for_unknown_task_type(self):
        """Should return None when no data for task type"""
        tracker = ModelAttributionTracker()
        tracker.record_completion(
            model_id="some/model",
            requested_model="some/model",
            provider="openrouter",
            task_type="coding",
            success=True,
            quality_score=80.0,
        )

        best = tracker.get_best_model_for_task_type("unknown_task_type")
        assert best is None

    def test_empty_tracker_top_models(self):
        """Should return empty list when no data"""
        tracker = ModelAttributionTracker()
        top = tracker.get_top_models(n=3)

        assert top == []

    def test_min_task_count_filter(self):
        """Should respect min_task_count in queries"""
        tracker = ModelAttributionTracker()

        # Model with only 1 task
        tracker.record_completion(
            model_id="few-tasks/model",
            requested_model="few-tasks/model",
            provider="openrouter",
            task_type="coding",
            success=True,
            quality_score=100.0,
        )

        # Model with 5 tasks
        for _ in range(5):
            tracker.record_completion(
                model_id="many-tasks/model",
                requested_model="many-tasks/model",
                provider="openrouter",
                task_type="coding",
                success=True,
                quality_score=80.0,
            )

        # With min_task_count=3, should only get the model with 5 tasks
        top = tracker.get_top_models(n=3, min_task_count=3)
        assert len(top) == 1
        assert top[0].model_id == "many-tasks/model"
