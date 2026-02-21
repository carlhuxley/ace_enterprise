"""BrokerAdvisor - recommends agents by capability fit.

The advisor acts as a Product Manager:
- Sees capabilities, not identities
- Recommends by skill match
- Human makes final decision

Key constraints:
- Cannot see agent identity
- Cannot see cost
- Cannot see business priorities
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.broker.capability_registry import CapabilityRegistry


@dataclass
class TaskRequirements:
    """Requirements for a task.

    Specifies capabilities needed with minimum proficiency levels.
    """

    task_id: str
    capabilities: dict[str, float]  # capability -> min proficiency
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Recommendation:
    """A recommended agent for a task.

    Contains only opaque agent_ref - no identity information.
    """

    agent_ref: str  # opaque reference
    capability_match: float  # 0-1, how well capabilities match
    meets_requirements: bool  # True if all requirements met
    success_rate: float | None = None  # historical success rate for capability


class BrokerAdvisor:
    """Advises on agent selection by capability fit.

    Acts as PM: sees capabilities, not identities.
    CAN SAY: "Capability python+testing has 93% success rate, 3 agents match"
    CAN'T SAY: "Agent A is Claude at $0.10/token"
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        capability_success_rates: dict[str, float] | None = None
    ) -> None:
        """Initialize advisor.

        Args:
            registry: The capability registry to query
            capability_success_rates: Historical success rates by capability (from audit)
        """
        self._registry = registry
        self._success_rates = capability_success_rates or {}

    def recommend(
        self,
        requirements: TaskRequirements,
        include_partial: bool = False
    ) -> list[Recommendation]:
        """Recommend agents for a task.

        Args:
            requirements: Task requirements (capabilities needed)
            include_partial: Include agents that only partially match

        Returns:
            List of recommendations, ranked by capability match
        """
        recommendations = []

        # Get all registered agents
        for agent_ref, agent in self._registry._agents.items():
            match_score, meets_all = self._calculate_match(
                agent.capabilities,
                requirements.capabilities
            )

            if meets_all or include_partial:
                # Calculate average success rate for required capabilities
                success_rate = self._get_avg_success_rate(requirements.capabilities)

                recommendations.append(Recommendation(
                    agent_ref=agent_ref,
                    capability_match=match_score,
                    meets_requirements=meets_all,
                    success_rate=success_rate
                ))

        # Sort by capability match (descending)
        recommendations.sort(key=lambda r: r.capability_match, reverse=True)

        return recommendations

    def _calculate_match(
        self,
        agent_caps: dict[str, float],
        required_caps: dict[str, float]
    ) -> tuple[float, bool]:
        """Calculate how well agent matches requirements.

        Returns:
            (match_score 0-1, meets_all_requirements)
        """
        if not required_caps:
            return 1.0, True

        total_score = 0.0
        meets_all = True

        for cap, min_prof in required_caps.items():
            agent_prof = agent_caps.get(cap, 0.0)

            if agent_prof >= min_prof:
                # Score based on how much agent exceeds minimum
                # Capped at 1.0 for the capability
                cap_score = min(agent_prof / min_prof, 1.5) / 1.5
                total_score += cap_score
            else:
                meets_all = False
                # Partial credit for having the capability
                if agent_prof > 0:
                    total_score += agent_prof / min_prof * 0.5

        match_score = total_score / len(required_caps)
        return match_score, meets_all

    def _get_avg_success_rate(
        self,
        capabilities: dict[str, float]
    ) -> float | None:
        """Get average success rate for capabilities."""
        if not self._success_rates:
            return None

        rates = [
            self._success_rates[cap]
            for cap in capabilities
            if cap in self._success_rates
        ]

        if not rates:
            return None

        return sum(rates) / len(rates)

    def get_summary(self, requirements: TaskRequirements) -> str:
        """Get a human-readable summary of recommendations.

        Describes capabilities and match quality WITHOUT revealing agent identities.
        """
        recommendations = self.recommend(requirements)

        if not recommendations:
            caps_str = ", ".join(requirements.capabilities.keys())
            return f"No agents match requirements for: {caps_str}"

        # Count matching agents
        full_matches = sum(1 for r in recommendations if r.meets_requirements)

        # Get capabilities
        caps_str = ", ".join(requirements.capabilities.keys())

        # Get success rate if available
        success_rate = recommendations[0].success_rate
        rate_str = f", {int(success_rate * 100)}% historical success rate" if success_rate else ""

        return (
            f"{full_matches} agents match requirements for {caps_str}{rate_str}. "
            f"Best match score: {recommendations[0].capability_match:.0%}"
        )
