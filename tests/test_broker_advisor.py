"""Tests for BrokerAdvisor - recommends agents by capability fit."""
import pytest


class TestTaskRequirements:
    """Tests for TaskRequirements dataclass."""

    def test_task_requirements_has_capabilities(self):
        """Should have capabilities with min proficiency."""
        from src.broker.advisor import TaskRequirements

        req = TaskRequirements(
            task_id="task-001",
            capabilities={"python": 0.8, "testing": 0.7}
        )

        assert req.capabilities["python"] == 0.8
        assert req.capabilities["testing"] == 0.7


class TestRecommendation:
    """Tests for Recommendation dataclass."""

    def test_recommendation_has_agent_ref_not_identity(self):
        """Should have opaque agent_ref, not identity."""
        from src.broker.advisor import Recommendation

        rec = Recommendation(
            agent_ref="agent-001",
            capability_match=0.95,
            meets_requirements=True
        )

        assert rec.agent_ref == "agent-001"
        assert not hasattr(rec, "agent_id")
        assert not hasattr(rec, "agent_name")
        assert not hasattr(rec, "cost")

    def test_recommendation_has_capability_match_score(self):
        """Should have capability match score 0-1."""
        from src.broker.advisor import Recommendation

        rec = Recommendation(
            agent_ref="agent-001",
            capability_match=0.95,
            meets_requirements=True
        )

        assert 0 <= rec.capability_match <= 1


class TestBrokerAdvisor:
    """Tests for BrokerAdvisor."""

    def test_recommend_returns_matching_agents(self):
        """Should return agents matching requirements."""
        from src.broker.advisor import BrokerAdvisor, TaskRequirements
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.9, "testing": 0.8})
        registry.register("agent-002", {"python": 0.5, "go": 0.9})

        advisor = BrokerAdvisor(registry)
        requirements = TaskRequirements(
            task_id="task-001",
            capabilities={"python": 0.8}
        )

        recommendations = advisor.recommend(requirements)

        agent_refs = [r.agent_ref for r in recommendations]
        assert "agent-001" in agent_refs
        assert "agent-002" not in agent_refs  # doesn't meet min proficiency

    def test_recommend_ranks_by_capability_match(self):
        """Should rank by how well capabilities match."""
        from src.broker.advisor import BrokerAdvisor, TaskRequirements
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.95, "testing": 0.9})
        registry.register("agent-002", {"python": 0.85, "testing": 0.85})

        advisor = BrokerAdvisor(registry)
        requirements = TaskRequirements(
            task_id="task-001",
            capabilities={"python": 0.8, "testing": 0.8}
        )

        recommendations = advisor.recommend(requirements)

        # agent-001 should rank higher (better match)
        assert recommendations[0].agent_ref == "agent-001"
        assert recommendations[0].capability_match > recommendations[1].capability_match

    def test_recommend_with_no_matches_returns_empty(self):
        """Should return empty list when no agents match."""
        from src.broker.advisor import BrokerAdvisor, TaskRequirements
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.5})

        advisor = BrokerAdvisor(registry)
        requirements = TaskRequirements(
            task_id="task-001",
            capabilities={"rust": 0.9}
        )

        recommendations = advisor.recommend(requirements)

        assert recommendations == []

    def test_recommend_includes_partial_matches_with_flag(self):
        """Should include partial matches when requested."""
        from src.broker.advisor import BrokerAdvisor, TaskRequirements
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.9})  # missing testing
        registry.register("agent-002", {"python": 0.9, "testing": 0.9})

        advisor = BrokerAdvisor(registry)
        requirements = TaskRequirements(
            task_id="task-001",
            capabilities={"python": 0.8, "testing": 0.8}
        )

        # With include_partial=True, should include agent-001
        recommendations = advisor.recommend(requirements, include_partial=True)

        agent_refs = [r.agent_ref for r in recommendations]
        assert "agent-001" in agent_refs
        assert "agent-002" in agent_refs

        # Partial match should be flagged
        partial = next(r for r in recommendations if r.agent_ref == "agent-001")
        assert partial.meets_requirements is False


class TestAdvisorWithSuccessRates:
    """Tests for advisor using historical success rates."""

    def test_recommend_uses_success_rates_when_available(self):
        """Should factor in historical success rates."""
        from src.broker.advisor import BrokerAdvisor, TaskRequirements
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.9})
        registry.register("agent-002", {"python": 0.9})

        # Provide success rates by capability
        success_rates = {"python": 0.85}

        advisor = BrokerAdvisor(registry, capability_success_rates=success_rates)
        requirements = TaskRequirements(
            task_id="task-001",
            capabilities={"python": 0.8}
        )

        recommendations = advisor.recommend(requirements)

        # Should include success rate in response
        assert recommendations[0].success_rate == 0.85


class TestAdvisorSummary:
    """Tests for advisor summary output."""

    def test_get_summary_describes_capabilities_not_agents(self):
        """Summary should describe capabilities, not reveal agents."""
        from src.broker.advisor import BrokerAdvisor, TaskRequirements
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.9, "testing": 0.8})
        registry.register("agent-002", {"python": 0.85, "testing": 0.9})

        advisor = BrokerAdvisor(registry, capability_success_rates={"python": 0.93})
        requirements = TaskRequirements(
            task_id="task-001",
            capabilities={"python": 0.8, "testing": 0.7}
        )

        summary = advisor.get_summary(requirements)

        # Should say things like "2 agents match", "93% success rate"
        assert "2" in summary  # 2 agents
        assert "python" in summary.lower()
        assert "93" in summary  # success rate
        # Should NOT reveal agent identities
        assert "agent-001" not in summary
        assert "agent-002" not in summary
