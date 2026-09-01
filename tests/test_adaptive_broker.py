"""Tests for AdaptiveBroker - audit-driven capability routing.

Bead: ace_enterprise-lfu

The AdaptiveBroker:
1. Uses PerformanceAggregator to learn from audit trail
2. Routes tasks to best agent based on historical performance
3. Maintains double-blind (sees metrics only, not content)
4. Returns routing decisions with confidence scores

Tests:
1. Routes to highest performing agent
2. Considers task type when routing
3. Considers complexity when routing
4. Returns confidence score with routing
5. Falls back when no history
6. Integrates with PerformanceAggregator
"""

from unittest.mock import MagicMock


class TestAdaptiveBrokerRouting:
    """Tests for adaptive routing based on performance."""

    def test_routes_to_highest_performer(self):
        """Should route to agent with best overall success rate."""
        from src.broker.adaptive_broker import AdaptiveBroker
        from src.broker.performance_aggregator import AgentPerformanceMetrics

        mock_aggregator = MagicMock()
        mock_aggregator.get_all_agent_metrics.return_value = {
            "agent-a": AgentPerformanceMetrics(
                agent_ref="agent-a",
                total_tasks=50,
                successful_tasks=45,  # 90%
            ),
            "agent-b": AgentPerformanceMetrics(
                agent_ref="agent-b",
                total_tasks=50,
                successful_tasks=30,  # 60%
            ),
        }

        broker = AdaptiveBroker(mock_aggregator)
        result = broker.route_task(task_type="general", complexity=2)

        assert result.selected_agent == "agent-a"
        assert result.confidence > 0.5

    def test_routes_by_task_type(self):
        """Should prefer agent with better performance on specific task type."""
        from src.broker.adaptive_broker import AdaptiveBroker
        from src.broker.performance_aggregator import AgentPerformanceMetrics

        mock_aggregator = MagicMock()
        mock_aggregator.get_all_agent_metrics.return_value = {
            "agent-a": AgentPerformanceMetrics(
                agent_ref="agent-a",
                total_tasks=50,
                successful_tasks=40,  # 80% overall
                success_by_task_type={"math": 0.95},  # Excellent at math
            ),
            "agent-b": AgentPerformanceMetrics(
                agent_ref="agent-b",
                total_tasks=50,
                successful_tasks=45,  # 90% overall
                success_by_task_type={"math": 0.50},  # Poor at math
            ),
        }

        broker = AdaptiveBroker(mock_aggregator)
        result = broker.route_task(task_type="math", complexity=2)

        # Should pick agent-a despite lower overall rate
        assert result.selected_agent == "agent-a"

    def test_routes_by_complexity(self):
        """Should prefer agent proven at the complexity level."""
        from src.broker.adaptive_broker import AdaptiveBroker
        from src.broker.performance_aggregator import AgentPerformanceMetrics

        mock_aggregator = MagicMock()
        mock_aggregator.get_all_agent_metrics.return_value = {
            "agent-a": AgentPerformanceMetrics(
                agent_ref="agent-a",
                total_tasks=50,
                successful_tasks=45,
                success_by_complexity={1: 0.95, 2: 0.90, 3: 0.40},  # Fails at 3
            ),
            "agent-b": AgentPerformanceMetrics(
                agent_ref="agent-b",
                total_tasks=50,
                successful_tasks=40,
                success_by_complexity={1: 0.80, 2: 0.80, 3: 0.85},  # Good at 3
            ),
        }

        broker = AdaptiveBroker(mock_aggregator)
        result = broker.route_task(task_type="coding", complexity=3)

        # Should pick agent-b for complexity 3
        assert result.selected_agent == "agent-b"


class TestRoutingConfidence:
    """Tests for confidence scoring."""

    def test_high_confidence_for_proven_agent(self):
        """Should return high confidence for agent with good track record."""
        from src.broker.adaptive_broker import AdaptiveBroker
        from src.broker.performance_aggregator import AgentPerformanceMetrics

        mock_aggregator = MagicMock()
        mock_aggregator.get_all_agent_metrics.return_value = {
            "agent-a": AgentPerformanceMetrics(
                agent_ref="agent-a",
                total_tasks=100,  # Many samples
                successful_tasks=95,  # 95% success
                success_by_task_type={"coding": 0.92},
                success_by_complexity={2: 0.90},
            ),
        }

        broker = AdaptiveBroker(mock_aggregator)
        result = broker.route_task(task_type="coding", complexity=2)

        assert result.confidence >= 0.85

    def test_low_confidence_for_new_agent(self):
        """Should return low confidence for agent with few samples."""
        from src.broker.adaptive_broker import AdaptiveBroker
        from src.broker.performance_aggregator import AgentPerformanceMetrics

        mock_aggregator = MagicMock()
        mock_aggregator.get_all_agent_metrics.return_value = {
            "agent-new": AgentPerformanceMetrics(
                agent_ref="agent-new",
                total_tasks=3,  # Few samples
                successful_tasks=3,  # 100% but low confidence
            ),
        }

        broker = AdaptiveBroker(mock_aggregator)
        result = broker.route_task(task_type="coding", complexity=2)

        # High success but low sample size = reduced confidence
        assert result.confidence < 0.7


class TestRoutingFallback:
    """Tests for fallback behavior."""

    def test_falls_back_when_no_history(self):
        """Should return fallback when no agents have history."""
        from src.broker.adaptive_broker import AdaptiveBroker

        mock_aggregator = MagicMock()
        mock_aggregator.get_all_agent_metrics.return_value = {}

        broker = AdaptiveBroker(mock_aggregator)
        broker.set_fallback_agent("default-agent")

        result = broker.route_task(task_type="coding", complexity=2)

        assert result.selected_agent == "default-agent"
        assert result.is_fallback is True
        assert result.confidence == 0.0

    def test_returns_all_candidates(self):
        """Should return list of candidate agents with scores."""
        from src.broker.adaptive_broker import AdaptiveBroker
        from src.broker.performance_aggregator import AgentPerformanceMetrics

        mock_aggregator = MagicMock()
        mock_aggregator.get_all_agent_metrics.return_value = {
            "agent-a": AgentPerformanceMetrics(
                agent_ref="agent-a",
                total_tasks=50,
                successful_tasks=45,
            ),
            "agent-b": AgentPerformanceMetrics(
                agent_ref="agent-b",
                total_tasks=50,
                successful_tasks=40,
            ),
            "agent-c": AgentPerformanceMetrics(
                agent_ref="agent-c",
                total_tasks=50,
                successful_tasks=35,
            ),
        }

        broker = AdaptiveBroker(mock_aggregator)
        result = broker.route_task(task_type="coding", complexity=2)

        # Should include candidates list
        assert len(result.candidates) >= 2
        # Should be sorted by score
        assert result.candidates[0][1] >= result.candidates[1][1]


class TestRoutingVerdict:
    """Tests for routing verdict (APPLY/ASK_FIRST/SKIP)."""

    def test_apply_verdict_for_high_confidence(self):
        """Should return APPLY for high confidence routing."""
        from src.broker.adaptive_broker import AdaptiveBroker
        from src.broker.performance_aggregator import AgentPerformanceMetrics

        mock_aggregator = MagicMock()
        mock_aggregator.get_all_agent_metrics.return_value = {
            "agent-a": AgentPerformanceMetrics(
                agent_ref="agent-a",
                total_tasks=100,
                successful_tasks=95,
                success_by_task_type={"coding": 0.95},
                success_by_complexity={1: 0.95},
            ),
        }

        broker = AdaptiveBroker(mock_aggregator)
        result = broker.route_task(task_type="coding", complexity=1)

        assert result.verdict == "APPLY"

    def test_ask_first_verdict_for_medium_confidence(self):
        """Should return ASK_FIRST for medium confidence."""
        from src.broker.adaptive_broker import AdaptiveBroker
        from src.broker.performance_aggregator import AgentPerformanceMetrics

        mock_aggregator = MagicMock()
        mock_aggregator.get_all_agent_metrics.return_value = {
            "agent-a": AgentPerformanceMetrics(
                agent_ref="agent-a",
                total_tasks=20,
                successful_tasks=12,  # 60%
                success_by_task_type={"coding": 0.60},
                success_by_complexity={3: 0.55},
            ),
        }

        broker = AdaptiveBroker(mock_aggregator)
        result = broker.route_task(task_type="coding", complexity=3)

        assert result.verdict == "ASK_FIRST"

    def test_skip_verdict_for_low_confidence(self):
        """Should return SKIP when no suitable agent."""
        from src.broker.adaptive_broker import AdaptiveBroker
        from src.broker.performance_aggregator import AgentPerformanceMetrics

        mock_aggregator = MagicMock()
        mock_aggregator.get_all_agent_metrics.return_value = {
            "agent-a": AgentPerformanceMetrics(
                agent_ref="agent-a",
                total_tasks=50,
                successful_tasks=15,  # 30% - poor
            ),
        }

        broker = AdaptiveBroker(mock_aggregator)
        result = broker.route_task(task_type="coding", complexity=5)

        # Low performance = SKIP verdict
        assert result.verdict in ["ASK_FIRST", "SKIP"]


class TestRoutingResult:
    """Tests for RoutingResult dataclass."""

    def test_routing_result_fields(self):
        """RoutingResult should have all required fields."""
        from src.broker.adaptive_broker import RoutingResult

        result = RoutingResult(
            selected_agent="agent-a",
            confidence=0.85,
            verdict="APPLY",
            candidates=[("agent-a", 0.85), ("agent-b", 0.60)],
            is_fallback=False,
            task_type="coding",
            complexity=2,
        )

        assert result.selected_agent == "agent-a"
        assert result.confidence == 0.85
        assert result.verdict == "APPLY"
        assert len(result.candidates) == 2
        assert result.is_fallback is False
        assert result.task_type == "coding"
        assert result.complexity == 2


class TestAllowedAgentsFilter:
    """route_task(allowed_agents=...) restricts routing to a candidate set."""

    def _aggregator(self):
        from src.broker.performance_aggregator import AgentPerformanceMetrics

        mock_aggregator = MagicMock()
        mock_aggregator.get_all_agent_metrics.return_value = {
            "agent-a": AgentPerformanceMetrics(
                agent_ref="agent-a", total_tasks=40, successful_tasks=38
            ),
            "agent-b": AgentPerformanceMetrics(
                agent_ref="agent-b", total_tasks=40, successful_tasks=20
            ),
            "agent-c": AgentPerformanceMetrics(
                agent_ref="agent-c", total_tasks=40, successful_tasks=39
            ),
        }
        mock_aggregator.get_all_model_profiles.return_value = {}
        return mock_aggregator

    def test_excludes_agents_outside_the_allowed_set(self):
        from src.broker.adaptive_broker import AdaptiveBroker

        broker = AdaptiveBroker(self._aggregator())
        result = broker.route_task(
            task_type="general", allowed_agents=["agent-a", "agent-b"]
        )
        # agent-c has the best record but isn't allowed.
        assert result.selected_agent == "agent-a"
        assert {ref for ref, _ in result.candidates} == {"agent-a", "agent-b"}

    def test_falls_back_when_no_allowed_agent_has_history(self):
        from src.broker.adaptive_broker import AdaptiveBroker

        broker = AdaptiveBroker(self._aggregator())
        broker.set_fallback_agent("agent-x")
        result = broker.route_task(
            task_type="general", allowed_agents=["agent-x", "agent-y"]
        )
        assert result.is_fallback is True
        assert result.selected_agent == "agent-x"

    def test_none_allowed_agents_keeps_all(self):
        from src.broker.adaptive_broker import AdaptiveBroker

        broker = AdaptiveBroker(self._aggregator())
        result = broker.route_task(task_type="general", allowed_agents=None)
        assert result.selected_agent == "agent-c"
