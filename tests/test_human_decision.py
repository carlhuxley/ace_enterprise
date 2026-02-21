"""Tests for HumanDecisionInterface - where humans see everything and decide."""
import pytest


class TestDecisionContext:
    """Tests for DecisionContext - full picture for human."""

    def test_context_includes_broker_recommendation(self):
        """Should include capability-based recommendation."""
        from src.broker.human_decision import DecisionContext

        ctx = DecisionContext(
            task_id="task-001",
            broker_summary="2 agents match python+testing, 93% success rate",
            recommendations=[
                {"agent_ref": "agent-001", "capability_match": 0.95},
                {"agent_ref": "agent-002", "capability_match": 0.85},
            ]
        )

        assert ctx.broker_summary is not None
        assert len(ctx.recommendations) == 2

    def test_context_includes_audit_data(self):
        """Should include full audit data (identities, costs from external tracker)."""
        from src.broker.human_decision import DecisionContext

        # Audit data comes from audit system, which gets costs from external tracker
        ctx = DecisionContext(
            task_id="task-001",
            broker_summary="2 agents match",
            recommendations=[],
            audit_data={
                "agent-001": {
                    "identity": "Claude Opus",
                    "cost_per_task": 0.15,  # from external cost tracker
                    "success_rate": 0.94,
                    "total_tasks": 150
                },
                "agent-002": {
                    "identity": "Qwen 2.5",
                    "cost_per_task": 0.002,  # from external cost tracker
                    "success_rate": 0.87,
                    "total_tasks": 320
                }
            }
        )

        assert ctx.audit_data["agent-001"]["identity"] == "Claude Opus"
        assert ctx.audit_data["agent-001"]["cost_per_task"] == 0.15


class TestHumanDecision:
    """Tests for HumanDecision - the human's choice."""

    def test_decision_records_chosen_agent(self):
        """Should record which agent was chosen."""
        from src.broker.human_decision import HumanDecision

        decision = HumanDecision(
            task_id="task-001",
            chosen_agent_ref="agent-002",
            decision_type="override",
            notes="Choosing cheaper option for bulk task"
        )

        assert decision.chosen_agent_ref == "agent-002"
        assert decision.decision_type == "override"

    def test_decision_types(self):
        """Should support different decision types."""
        from src.broker.human_decision import HumanDecision

        # Accept recommendation
        d1 = HumanDecision(
            task_id="task-001",
            chosen_agent_ref="agent-001",
            decision_type="accept"
        )
        assert d1.decision_type == "accept"

        # Override
        d2 = HumanDecision(
            task_id="task-001",
            chosen_agent_ref="agent-002",
            decision_type="override"
        )
        assert d2.decision_type == "override"

        # Broadcast to multiple
        d3 = HumanDecision(
            task_id="task-001",
            chosen_agent_ref=None,
            decision_type="broadcast",
            broadcast_to=["agent-001", "agent-002", "agent-003"]
        )
        assert d3.decision_type == "broadcast"
        assert len(d3.broadcast_to) == 3


class TestHumanDecisionInterface:
    """Tests for HumanDecisionInterface."""

    def test_get_context_combines_broker_and_audit(self):
        """Should combine broker recommendation with audit data."""
        from src.broker.human_decision import HumanDecisionInterface
        from src.broker.advisor import BrokerAdvisor, TaskRequirements
        from src.broker.capability_registry import CapabilityRegistry

        # Setup registry and advisor
        registry = CapabilityRegistry()
        registry.register("agent-001", {"python": 0.9})
        registry.register("agent-002", {"python": 0.85})

        advisor = BrokerAdvisor(registry)

        # Audit data (from audit system, costs from external tracker)
        audit_data = {
            "agent-001": {"identity": "Claude", "cost_per_task": 0.10},
            "agent-002": {"identity": "Qwen", "cost_per_task": 0.01}
        }

        interface = HumanDecisionInterface(advisor, audit_data)

        requirements = TaskRequirements(
            task_id="task-001",
            capabilities={"python": 0.8}
        )

        context = interface.get_context(requirements)

        # Should have broker summary
        assert "agent" in context.broker_summary.lower() or "match" in context.broker_summary.lower()
        # Should have audit data
        assert context.audit_data["agent-001"]["identity"] == "Claude"

    def test_record_decision(self):
        """Should record human decision."""
        from src.broker.human_decision import HumanDecisionInterface, HumanDecision
        from src.broker.advisor import BrokerAdvisor
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        advisor = BrokerAdvisor(registry)
        interface = HumanDecisionInterface(advisor, {})

        decision = HumanDecision(
            task_id="task-001",
            chosen_agent_ref="agent-002",
            decision_type="override",
            notes="Testing cheaper option"
        )

        result = interface.record_decision(decision)

        assert result.recorded is True
        assert result.task_id == "task-001"

    def test_get_decision_history(self):
        """Should retrieve decision history."""
        from src.broker.human_decision import HumanDecisionInterface, HumanDecision
        from src.broker.advisor import BrokerAdvisor
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        advisor = BrokerAdvisor(registry)
        interface = HumanDecisionInterface(advisor, {})

        # Record some decisions
        interface.record_decision(HumanDecision(
            task_id="task-001",
            chosen_agent_ref="agent-001",
            decision_type="accept"
        ))
        interface.record_decision(HumanDecision(
            task_id="task-002",
            chosen_agent_ref="agent-002",
            decision_type="override"
        ))

        history = interface.get_decision_history()

        assert len(history) == 2


class TestDecisionAnalytics:
    """Tests for decision analytics."""

    def test_get_override_rate(self):
        """Should calculate how often humans override recommendations."""
        from src.broker.human_decision import HumanDecisionInterface, HumanDecision
        from src.broker.advisor import BrokerAdvisor
        from src.broker.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry()
        advisor = BrokerAdvisor(registry)
        interface = HumanDecisionInterface(advisor, {})

        # 3 accepts, 1 override
        for i in range(3):
            interface.record_decision(HumanDecision(
                task_id=f"task-{i}",
                chosen_agent_ref="agent-001",
                decision_type="accept"
            ))
        interface.record_decision(HumanDecision(
            task_id="task-3",
            chosen_agent_ref="agent-002",
            decision_type="override"
        ))

        stats = interface.get_decision_stats()

        assert stats["total_decisions"] == 4
        assert stats["accepts"] == 3
        assert stats["overrides"] == 1
        assert stats["override_rate"] == 0.25
