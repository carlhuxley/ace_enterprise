"""Audit Analysis Dashboard - insights for humans.

The dashboard reveals what the broker cannot see:
- Agent identities (maps opaque agent_ref to model/provider)
- Costs (injected from external tracker)
- Performance patterns (success rates, task type strengths)
- Winning combinations (optimal teams for task types)

This is where humans get full visibility to make informed decisions.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentPerformance:
    """Performance metrics for an agent."""

    agent_ref: str
    total_tasks: int
    successful_tasks: int
    success_rate: float


@dataclass
class AgentIdentity:
    """Identity information for an agent (hidden from broker)."""

    display_name: str
    model_id: str
    provider: str


class AuditDashboard:
    """Dashboard for analyzing audit data.

    Provides insights that the broker cannot see:
    - Full agent identities
    - Cost analysis from external tracker
    - Performance patterns and trends
    - Optimal team suggestions
    """

    def __init__(self, audit_events: list[dict[str, Any]]) -> None:
        """Initialize dashboard with audit events.

        Args:
            audit_events: List of audit event dicts
        """
        self._events = audit_events
        self._cost_data: dict[str, dict[str, Any]] = {}
        self._identities: dict[str, AgentIdentity] = {}
        self._benchmark_data: dict[str, dict[str, Any]] = {}

    def get_agent_performance(self) -> dict[str, AgentPerformance]:
        """Calculate performance metrics per agent.

        Returns:
            Dict mapping agent_ref to AgentPerformance
        """
        # Count successes and totals per agent
        agent_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total": 0, "success": 0}
        )

        for event in self._events:
            if event.get("event_type") == "CYCLE_COMPLETED":
                agent_id = event["actor_id"]
                agent_stats[agent_id]["total"] += 1
                if event.get("payload", {}).get("success"):
                    agent_stats[agent_id]["success"] += 1

        # Convert to AgentPerformance objects
        result = {}
        for agent_ref, stats in agent_stats.items():
            total = stats["total"]
            success = stats["success"]
            result[agent_ref] = AgentPerformance(
                agent_ref=agent_ref,
                total_tasks=total,
                successful_tasks=success,
                success_rate=success / total if total > 0 else 0.0,
            )

        return result

    def inject_cost_data(self, cost_data: dict[str, dict[str, Any]]) -> None:
        """Inject cost data from external tracker.

        Args:
            cost_data: Dict mapping agent_ref to cost info
                       {agent_ref: {"total_cost": float, "tasks": int}}
        """
        self._cost_data = cost_data

    def get_cost_analysis(self) -> dict[str, dict[str, Any]]:
        """Get cost analysis per agent.

        Returns:
            Dict mapping agent_ref to cost metrics
        """
        result = {}
        for agent_ref, data in self._cost_data.items():
            total_cost = data.get("total_cost", 0)
            tasks = data.get("tasks", 0)
            result[agent_ref] = {
                "total_cost": total_cost,
                "tasks": tasks,
                "cost_per_task": total_cost / tasks if tasks > 0 else 0,
            }
        return result

    def get_cost_ranking(self) -> list[str]:
        """Rank agents by cost efficiency (cheapest first).

        Returns:
            List of agent_refs sorted by cost_per_task ascending
        """
        analysis = self.get_cost_analysis()
        sorted_agents = sorted(
            analysis.keys(),
            key=lambda a: analysis[a]["cost_per_task"]
        )
        return sorted_agents

    def register_identity(self, agent_ref: str, identity: AgentIdentity) -> None:
        """Register identity for an agent.

        Args:
            agent_ref: Opaque agent reference
            identity: Full identity information
        """
        self._identities[agent_ref] = identity

    def get_identity(self, agent_ref: str) -> AgentIdentity | None:
        """Get identity for an agent.

        Args:
            agent_ref: Opaque agent reference

        Returns:
            AgentIdentity or None if not registered
        """
        return self._identities.get(agent_ref)

    def get_full_report(self) -> dict[str, dict[str, Any]]:
        """Get full report with performance and identity.

        Returns:
            Dict mapping agent_ref to full details
        """
        performance = self.get_agent_performance()
        costs = self.get_cost_analysis()

        result = {}
        # Include all agents from performance
        for agent_ref, perf in performance.items():
            result[agent_ref] = {
                "performance": {
                    "total_tasks": perf.total_tasks,
                    "successful_tasks": perf.successful_tasks,
                    "success_rate": perf.success_rate,
                },
            }
            if agent_ref in self._identities:
                identity = self._identities[agent_ref]
                result[agent_ref]["identity"] = {
                    "display_name": identity.display_name,
                    "model_id": identity.model_id,
                    "provider": identity.provider,
                }
            if agent_ref in costs:
                result[agent_ref]["costs"] = costs[agent_ref]

        return result

    def get_task_type_strengths(self) -> dict[str, dict[str, Any]]:
        """Identify which agents excel at which task types.

        Returns:
            Dict mapping task_type to best agent info
        """
        # Aggregate by task type and agent
        task_agent_stats: dict[str, dict[str, dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: {"total": 0, "success": 0})
        )

        for event in self._events:
            if event.get("event_type") == "CYCLE_COMPLETED":
                payload = event.get("payload", {})
                task_type = payload.get("task_type")
                if task_type:
                    agent_id = event["actor_id"]
                    task_agent_stats[task_type][agent_id]["total"] += 1
                    if payload.get("success"):
                        task_agent_stats[task_type][agent_id]["success"] += 1

        # Find best agent per task type
        result = {}
        for task_type, agent_stats in task_agent_stats.items():
            best_agent = None
            best_rate = -1.0

            for agent_id, stats in agent_stats.items():
                if stats["total"] > 0:
                    rate = stats["success"] / stats["total"]
                    if rate > best_rate:
                        best_rate = rate
                        best_agent = agent_id

            result[task_type] = {
                "best_agent": best_agent,
                "success_rate": best_rate,
            }

        return result

    def suggest_team(self, task_types: list[str]) -> list[str]:
        """Suggest optimal team based on historical performance.

        Args:
            task_types: List of task types needed

        Returns:
            List of agent_refs for optimal team
        """
        strengths = self.get_task_type_strengths()
        team = set()

        for task_type in task_types:
            if task_type in strengths:
                best_agent = strengths[task_type].get("best_agent")
                if best_agent:
                    team.add(best_agent)

        return list(team)

    def set_benchmark_data(self, benchmark_data: dict[str, dict[str, Any]]) -> None:
        """Set benchmark data for comparison.

        Args:
            benchmark_data: Dict mapping agent_ref to benchmark scores
        """
        self._benchmark_data = benchmark_data

    def compare_to_benchmarks(self) -> dict[str, dict[str, Any]]:
        """Compare production performance to benchmark scores.

        Returns:
            Dict with production vs benchmark comparison
        """
        performance = self.get_agent_performance()

        result = {}
        for agent_ref, bench_data in self._benchmark_data.items():
            prod_rate = 0.0
            if agent_ref in performance:
                prod_rate = performance[agent_ref].success_rate

            result[agent_ref] = {
                "production_success_rate": prod_rate,
                "benchmark_score": bench_data.get("swe_bench_score", 0.0),
            }

        return result

    def get_summary(self) -> dict[str, Any]:
        """Generate summary of dashboard data.

        Returns:
            Summary dict with key metrics
        """
        performance = self.get_agent_performance()
        total_tasks = sum(p.total_tasks for p in performance.values())

        return {
            "agents": list(performance.keys()),
            "total_tasks": total_tasks,
            "agents_with_identity": list(self._identities.keys()),
            "agents_with_costs": list(self._cost_data.keys()),
        }
