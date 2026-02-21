"""Tests for PerformanceAggregator - audit-driven capability learning.

Bead: ace_enterprise-lfu

Tests that the aggregator:
1. Extracts ONLY metrics from audit (no content)
2. Calculates success rates correctly
3. Tracks performance by complexity level
4. Tracks performance by task type
5. Suggests best agent based on history
6. Maintains double-blind (never exposes content)
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from src.audit.schemas import AuditEvent, AuditEventType


class TestPerformanceAggregatorMetricsOnly:
    """Tests that aggregator extracts ONLY metrics, never content."""

    def test_extracts_success_rate_not_content(self):
        """Should extract success boolean, not output content."""
        from src.broker.performance_aggregator import PerformanceAggregator

        mock_store = MagicMock()
        mock_store.query.return_value = MagicMock(events=[
            MagicMock(
                actor_id="agent-001",
                event_type=AuditEventType.CYCLE_COMPLETED,
                timestamp=datetime.now(),
                payload={
                    "success": True,
                    "output": "THIS SHOULD NOT BE EXTRACTED",
                    "prompt": "THIS SHOULD NOT BE EXTRACTED",
                }
            )
        ])

        aggregator = PerformanceAggregator(mock_store)
        metrics = aggregator.get_agent_metrics("agent-001")

        # Should have success rate
        assert metrics.success_rate == 1.0

        # Should NOT have content anywhere in metrics
        metrics_str = str(metrics)
        assert "THIS SHOULD NOT BE EXTRACTED" not in metrics_str

    def test_extracts_latency_not_prompt(self):
        """Should extract elapsed time, not prompt content."""
        from src.broker.performance_aggregator import PerformanceAggregator

        mock_store = MagicMock()
        mock_store.query.return_value = MagicMock(events=[
            MagicMock(
                actor_id="agent-001",
                event_type=AuditEventType.CYCLE_COMPLETED,
                timestamp=datetime.now(),
                payload={
                    "success": True,
                    "elapsed_seconds": 45.5,
                    "prompt": "Secret business logic",
                }
            )
        ])

        aggregator = PerformanceAggregator(mock_store)
        metrics = aggregator.get_agent_metrics("agent-001")

        assert metrics.avg_latency_seconds == 45.5
        assert "Secret" not in str(metrics)


class TestSuccessRateCalculation:
    """Tests for success rate calculations."""

    def test_calculates_success_rate(self):
        """Should calculate success rate from events."""
        from src.broker.performance_aggregator import PerformanceAggregator

        mock_store = MagicMock()
        mock_store.query.return_value = MagicMock(events=[
            MagicMock(
                actor_id="agent-001",
                event_type=AuditEventType.CYCLE_COMPLETED,
                timestamp=datetime.now(),
                payload={"success": True}
            ),
            MagicMock(
                actor_id="agent-001",
                event_type=AuditEventType.CYCLE_COMPLETED,
                timestamp=datetime.now(),
                payload={"success": True}
            ),
            MagicMock(
                actor_id="agent-001",
                event_type=AuditEventType.CYCLE_COMPLETED,
                timestamp=datetime.now(),
                payload={"success": False}
            ),
        ])

        aggregator = PerformanceAggregator(mock_store)
        metrics = aggregator.get_agent_metrics("agent-001")

        assert metrics.total_tasks == 3
        assert metrics.successful_tasks == 2
        assert metrics.failed_tasks == 1
        assert metrics.success_rate == pytest.approx(0.666, rel=0.01)

    def test_zero_tasks_returns_zero_success_rate(self):
        """Should return 0 success rate for no tasks."""
        from src.broker.performance_aggregator import PerformanceAggregator

        mock_store = MagicMock()
        mock_store.query.return_value = MagicMock(events=[])

        aggregator = PerformanceAggregator(mock_store)
        metrics = aggregator.get_agent_metrics("agent-001")

        assert metrics.total_tasks == 0
        assert metrics.success_rate == 0.0


class TestComplexityTracking:
    """Tests for complexity level tracking."""

    def test_tracks_success_by_complexity(self):
        """Should track success rates per complexity level."""
        from src.broker.performance_aggregator import PerformanceAggregator

        mock_store = MagicMock()
        mock_store.query.return_value = MagicMock(events=[
            # Complexity 1: 2/2 success
            MagicMock(actor_id="a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True, "complexity": 1}),
            MagicMock(actor_id="a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True, "complexity": 1}),
            # Complexity 3: 1/2 success
            MagicMock(actor_id="a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True, "complexity": 3}),
            MagicMock(actor_id="a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": False, "complexity": 3}),
        ])

        aggregator = PerformanceAggregator(mock_store)
        metrics = aggregator.get_agent_metrics("a")

        assert metrics.success_by_complexity[1] == 1.0
        assert metrics.success_by_complexity[3] == 0.5

    def test_can_handle_complexity_check(self):
        """Should correctly check if agent can handle complexity."""
        from src.broker.performance_aggregator import AgentPerformanceMetrics

        metrics = AgentPerformanceMetrics(
            agent_ref="test",
            success_by_complexity={1: 0.95, 2: 0.80, 3: 0.40}
        )

        assert metrics.can_handle_complexity(1, min_success_rate=0.7) is True
        assert metrics.can_handle_complexity(2, min_success_rate=0.7) is True
        assert metrics.can_handle_complexity(3, min_success_rate=0.7) is False
        assert metrics.can_handle_complexity(4, min_success_rate=0.7) is False


class TestTaskTypeTracking:
    """Tests for task type tracking."""

    def test_tracks_success_by_task_type(self):
        """Should track success rates per task type."""
        from src.broker.performance_aggregator import PerformanceAggregator

        mock_store = MagicMock()
        mock_store.query.return_value = MagicMock(events=[
            MagicMock(actor_id="a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True, "task_type": "math"}),
            MagicMock(actor_id="a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True, "task_type": "math"}),
            MagicMock(actor_id="a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": False, "task_type": "coding"}),
        ])

        aggregator = PerformanceAggregator(mock_store)
        metrics = aggregator.get_agent_metrics("a")

        assert metrics.success_by_task_type["math"] == 1.0
        assert metrics.success_by_task_type["coding"] == 0.0


class TestBestAgentSuggestion:
    """Tests for best agent suggestion."""

    def test_suggests_best_agent_by_success_rate(self):
        """Should suggest agent with highest success rate."""
        from src.broker.performance_aggregator import PerformanceAggregator

        mock_store = MagicMock()
        mock_store.query.return_value = MagicMock(events=[
            # Agent A: 90% success
            MagicMock(actor_id="agent-a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True}),
            MagicMock(actor_id="agent-a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True}),
            MagicMock(actor_id="agent-a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True}),
            MagicMock(actor_id="agent-a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True}),
            MagicMock(actor_id="agent-a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": False}),
            # Agent B: 60% success
            MagicMock(actor_id="agent-b", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True}),
            MagicMock(actor_id="agent-b", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True}),
            MagicMock(actor_id="agent-b", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True}),
            MagicMock(actor_id="agent-b", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": False}),
            MagicMock(actor_id="agent-b", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": False}),
        ])

        aggregator = PerformanceAggregator(mock_store)
        suggestions = aggregator.get_best_agent_for_task()

        # Agent A should be first (higher success rate)
        assert len(suggestions) >= 1
        assert suggestions[0][0] == "agent-a"

    def test_suggests_agent_for_task_type(self):
        """Should suggest agent best at specific task type."""
        from src.broker.performance_aggregator import PerformanceAggregator

        mock_store = MagicMock()
        mock_store.query.return_value = MagicMock(events=[
            # Agent A: good at math
            MagicMock(actor_id="agent-a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True, "task_type": "math"}),
            MagicMock(actor_id="agent-a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True, "task_type": "math"}),
            MagicMock(actor_id="agent-a", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": False, "task_type": "coding"}),
            # Agent B: good at coding
            MagicMock(actor_id="agent-b", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": False, "task_type": "math"}),
            MagicMock(actor_id="agent-b", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True, "task_type": "coding"}),
            MagicMock(actor_id="agent-b", timestamp=datetime.now(),
                      event_type=AuditEventType.CYCLE_COMPLETED,
                      payload={"success": True, "task_type": "coding"}),
        ])

        aggregator = PerformanceAggregator(mock_store)

        # For math tasks, suggest agent-a
        math_suggestions = aggregator.get_best_agent_for_task(task_type="math")
        assert math_suggestions[0][0] == "agent-a"

        # For coding tasks, suggest agent-b
        coding_suggestions = aggregator.get_best_agent_for_task(task_type="coding")
        assert coding_suggestions[0][0] == "agent-b"


class TestReliabilityScore:
    """Tests for reliability scoring based on sample size."""

    def test_low_sample_reduces_confidence(self):
        """Should reduce confidence for agents with few samples."""
        from src.broker.performance_aggregator import AgentPerformanceMetrics

        # High success but few samples
        metrics_low = AgentPerformanceMetrics(
            agent_ref="new-agent",
            total_tasks=3,
            successful_tasks=3,
        )

        # Same success rate but many samples
        metrics_high = AgentPerformanceMetrics(
            agent_ref="proven-agent",
            total_tasks=50,
            successful_tasks=50,
        )

        # Both have 100% success rate
        assert metrics_low.success_rate == 1.0
        assert metrics_high.success_rate == 1.0

        # But reliability should differ
        assert metrics_low.reliability_score < metrics_high.reliability_score
