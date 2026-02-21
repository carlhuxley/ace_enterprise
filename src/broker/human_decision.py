"""HumanDecisionInterface - where humans see everything and decide.

The human sees what the broker cannot:
- Agent identities
- Costs (from external tracker via audit)
- Business context

The human makes final assignment decisions.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.broker.advisor import BrokerAdvisor, TaskRequirements


@dataclass
class DecisionContext:
    """Full context for human decision-making.

    Combines broker recommendation with audit data.
    Human sees everything the broker cannot.
    """

    task_id: str
    broker_summary: str
    recommendations: list[dict[str, Any]]
    audit_data: dict[str, dict[str, Any]] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class HumanDecision:
    """A human's assignment decision.

    Records what the human chose and why.
    """

    task_id: str
    chosen_agent_ref: str | None  # None for broadcast
    decision_type: str  # "accept", "override", "broadcast"
    notes: str | None = None
    broadcast_to: list[str] = field(default_factory=list)
    decided_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class DecisionResult:
    """Result of recording a decision."""

    recorded: bool
    task_id: str
    decision_id: str | None = None


class HumanDecisionInterface:
    """Interface for human decision-making.

    Combines broker recommendations with audit data to give
    humans full visibility for assignment decisions.
    """

    def __init__(
        self,
        advisor: BrokerAdvisor,
        audit_data: dict[str, dict[str, Any]]
    ) -> None:
        """Initialize interface.

        Args:
            advisor: The broker advisor for recommendations
            audit_data: Audit data with agent identities and costs
                       (costs come from external tracker via audit)
        """
        self._advisor = advisor
        self._audit_data = audit_data
        self._decisions: list[HumanDecision] = []

    def get_context(self, requirements: TaskRequirements) -> DecisionContext:
        """Get full decision context for a task.

        Combines:
        - Broker recommendation (capability-based, no identity)
        - Audit data (identities, costs from external tracker)

        Args:
            requirements: Task requirements

        Returns:
            DecisionContext with full picture for human
        """
        # Get broker recommendation
        recommendations = self._advisor.recommend(requirements)
        summary = self._advisor.get_summary(requirements)

        # Convert recommendations to dicts
        rec_dicts = [
            {
                "agent_ref": r.agent_ref,
                "capability_match": r.capability_match,
                "meets_requirements": r.meets_requirements,
                "success_rate": r.success_rate
            }
            for r in recommendations
        ]

        return DecisionContext(
            task_id=requirements.task_id,
            broker_summary=summary,
            recommendations=rec_dicts,
            audit_data=self._audit_data
        )

    def record_decision(self, decision: HumanDecision) -> DecisionResult:
        """Record a human assignment decision.

        Args:
            decision: The human's decision

        Returns:
            DecisionResult confirming recording
        """
        self._decisions.append(decision)

        return DecisionResult(
            recorded=True,
            task_id=decision.task_id,
            decision_id=f"dec-{len(self._decisions)}"
        )

    def get_decision_history(self) -> list[HumanDecision]:
        """Get history of all decisions."""
        return list(self._decisions)

    def get_decision_stats(self) -> dict[str, Any]:
        """Get statistics about human decisions.

        Useful for understanding:
        - How often humans override broker recommendations
        - Which decision types are most common
        """
        total = len(self._decisions)
        if total == 0:
            return {
                "total_decisions": 0,
                "accepts": 0,
                "overrides": 0,
                "broadcasts": 0,
                "override_rate": 0.0
            }

        accepts = sum(1 for d in self._decisions if d.decision_type == "accept")
        overrides = sum(1 for d in self._decisions if d.decision_type == "override")
        broadcasts = sum(1 for d in self._decisions if d.decision_type == "broadcast")

        return {
            "total_decisions": total,
            "accepts": accepts,
            "overrides": overrides,
            "broadcasts": broadcasts,
            "override_rate": overrides / total if total > 0 else 0.0
        }
