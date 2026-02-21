"""CapabilityRegistry - anonymous agent capability tracking.

T-Shaped Agent Model:
- Each agent has breadth (many capabilities) and depth (core strength)
- Core strength is implicit - the highest-rated capability
- Proficiency ratings: 0.0 to 1.0
- agent_ref is opaque - no identity information
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import combinations


@dataclass
class AgentCapabilities:
    """Agent capabilities with proficiency ratings.

    T-shaped model: breadth across capabilities, depth in core strength.
    """

    agent_ref: str
    capabilities: dict[str, float] = field(default_factory=dict)
    declared_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def core_strength(self) -> str | None:
        """Return the highest-rated capability (implicit core strength).

        When tied, returns first alphabetically for consistency.
        """
        if not self.capabilities:
            return None

        max_proficiency = max(self.capabilities.values())
        top_capabilities = [
            cap for cap, prof in self.capabilities.items()
            if prof == max_proficiency
        ]
        return sorted(top_capabilities)[0]


class CapabilityRegistry:
    """Registry for anonymous agent capabilities.

    Key constraint: No identity information stored.
    agent_ref is opaque to the broker.
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentCapabilities] = {}

    def register(
        self,
        agent_ref: str,
        capabilities: dict[str, float]
    ) -> AgentCapabilities:
        """Register or update agent capabilities.

        Args:
            agent_ref: Opaque agent reference (not identity)
            capabilities: Dict of capability -> proficiency (0.0-1.0)

        Returns:
            The registered AgentCapabilities
        """
        agent = AgentCapabilities(
            agent_ref=agent_ref,
            capabilities=capabilities
        )
        self._agents[agent_ref] = agent
        return agent

    def get(self, agent_ref: str) -> AgentCapabilities | None:
        """Get agent capabilities by reference."""
        return self._agents.get(agent_ref)

    def find_by_capability(
        self,
        capability: str,
        min_proficiency: float = 0.0
    ) -> list[str]:
        """Find agents with a capability at minimum proficiency.

        Args:
            capability: The capability to search for
            min_proficiency: Minimum proficiency threshold (0.0-1.0)

        Returns:
            List of agent_ref values matching criteria
        """
        return [
            agent.agent_ref
            for agent in self._agents.values()
            if capability in agent.capabilities
            and agent.capabilities[capability] >= min_proficiency
        ]

    def find_balanced_team(
        self,
        needs: dict[str, float]
    ) -> list[str]:
        """Find smallest team that covers all needs.

        Args:
            needs: Dict of capability -> minimum proficiency required

        Returns:
            List of agent_ref values forming a balanced team,
            or empty list if needs cannot be met.
        """
        if not needs:
            return []

        agents = list(self._agents.values())

        # Check if any single agent can cover all needs
        for agent in agents:
            if self._agent_covers_needs(agent, needs):
                return [agent.agent_ref]

        # Try combinations of increasing size
        for team_size in range(2, len(agents) + 1):
            for team in combinations(agents, team_size):
                if self._team_covers_needs(team, needs):
                    return [a.agent_ref for a in team]

        return []

    def _agent_covers_needs(
        self,
        agent: AgentCapabilities,
        needs: dict[str, float]
    ) -> bool:
        """Check if single agent covers all needs."""
        for cap, min_prof in needs.items():
            if cap not in agent.capabilities:
                return False
            if agent.capabilities[cap] < min_prof:
                return False
        return True

    def _team_covers_needs(
        self,
        team: tuple[AgentCapabilities, ...],
        needs: dict[str, float]
    ) -> bool:
        """Check if team together covers all needs."""
        for cap, min_prof in needs.items():
            # At least one team member must cover this need
            covered = any(
                cap in agent.capabilities and agent.capabilities[cap] >= min_prof
                for agent in team
            )
            if not covered:
                return False
        return True

    def get_capability_stats(self) -> dict[str, dict]:
        """Get statistics about registered capabilities.

        Returns:
            Dict of capability -> {agent_count, avg_proficiency}
        """
        stats: dict[str, dict] = {}

        for agent in self._agents.values():
            for cap, prof in agent.capabilities.items():
                if cap not in stats:
                    stats[cap] = {"agent_count": 0, "total_proficiency": 0.0}
                stats[cap]["agent_count"] += 1
                stats[cap]["total_proficiency"] += prof

        # Calculate averages
        for cap in stats:
            count = stats[cap]["agent_count"]
            total = stats[cap]["total_proficiency"]
            stats[cap]["avg_proficiency"] = total / count if count > 0 else 0.0
            del stats[cap]["total_proficiency"]

        return stats
