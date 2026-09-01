"""Adaptive Broker - Routes tasks based on learned performance.

Bead: ace_enterprise-lfu

The AdaptiveBroker uses the PerformanceAggregator to learn from
historical audit data and route tasks to the best agent.

Key principles:
- Double-blind: Only sees metrics, never content
- Learns over time: Performance improves with more data
- Transparent: Returns confidence and all candidates
- Fallback-safe: Has default behavior when no history

Verdicts:
- APPLY: High confidence, proceed with routing
- ASK_FIRST: Medium confidence, suggest but confirm
- SKIP: Low confidence, need manual selection
"""

import logging
from dataclasses import dataclass

from src.broker.performance_aggregator import (
    AgentPerformanceMetrics,
    ModelProfile,
    PerformanceAggregator,
)

logger = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    """Result of adaptive routing decision."""

    selected_agent: str
    confidence: float
    verdict: str
    candidates: list[tuple[str, float]]
    is_fallback: bool
    task_type: str | None = None
    complexity: int | None = None


ROUTING_BEST_QUALITY = "BEST_QUALITY"
ROUTING_BUDGET = "BUDGET"
ROUTING_BALANCED = "BALANCED"
ROUTING_PARETO = "PARETO"


@dataclass
class BrokerConfig:
    """Configuration for AdaptiveBroker."""

    apply_threshold: float = 0.70
    ask_threshold: float = 0.35
    task_type_weight: float = 0.3
    complexity_weight: float = 0.3
    overall_weight: float = 0.4
    fallback_agent: str | None = None

    # Cost-aware routing
    routing_mode: str = ROUTING_BEST_QUALITY
    max_cost_per_task: float | None = None   # hard cap; None = no limit
    cost_quality_tradeoff: float = 0.5       # 0 = cheapest, 1 = best quality
    acceptable_quality_delta: float = 0.05   # max quality loss tolerated in BUDGET mode

    # Latency-constrained routing
    max_latency_seconds: float | None = None  # hard cap on avg latency; None = no limit


class AdaptiveBroker:
    """Routes tasks to best agent based on historical performance."""

    def __init__(
        self,
        aggregator: PerformanceAggregator,
        config: BrokerConfig | None = None,
    ):
        self._aggregator = aggregator
        self._config = config or BrokerConfig()

    def route_task(
        self,
        task_type: str | None = None,
        complexity: int | None = None,
        allowed_agents: list[str] | None = None,
    ) -> RoutingResult:
        """Route task to best agent based on performance history and routing mode.

        allowed_agents restricts routing to that set of agent refs (e.g. the
        models actually configured and reachable for this run). Agents in the
        set with no audit history are simply not scored -- routing can only
        rank agents it has data on -- so if none of the allowed agents have
        history the result is a fallback.
        """
        all_metrics = self._aggregator.get_all_agent_metrics()

        if allowed_agents is not None:
            allowed = set(allowed_agents)
            all_metrics = {ref: m for ref, m in all_metrics.items() if ref in allowed}

        if not all_metrics:
            return self._fallback_result(task_type, complexity)

        profiles = self._aggregator.get_all_model_profiles()

        candidates = []
        for agent_ref, metrics in all_metrics.items():
            profile = profiles.get(agent_ref)
            score = self._calculate_score(metrics, task_type, complexity, profile)
            candidates.append((agent_ref, score))

        candidates = self._filter_by_latency(candidates, all_metrics)
        if not candidates:
            return self._fallback_result(task_type, complexity)

        candidates = self._apply_routing_mode(candidates, all_metrics)

        candidates.sort(key=lambda x: x[1], reverse=True)
        selected_agent, confidence = candidates[0]
        verdict = self._get_verdict(confidence)

        return RoutingResult(
            selected_agent=selected_agent,
            confidence=confidence,
            verdict=verdict,
            candidates=candidates,
            is_fallback=False,
            task_type=task_type,
            complexity=complexity,
        )

    def _filter_by_latency(
        self,
        candidates: list[tuple[str, float]],
        all_metrics: dict,
    ) -> list[tuple[str, float]]:
        """Remove candidates exceeding max_latency_seconds.

        Agents with no latency history (avg_latency_seconds == 0) are kept —
        absence of data is not evidence of slowness.  Falls back to the full
        list if every agent exceeds the cap.
        """
        cap = self._config.max_latency_seconds
        if cap is None:
            return candidates

        within = [
            (ref, score)
            for ref, score in candidates
            if all_metrics[ref].avg_latency_seconds == 0
            or all_metrics[ref].avg_latency_seconds <= cap
        ]
        return within if within else candidates

    def _apply_routing_mode(
        self,
        candidates: list[tuple[str, float]],
        all_metrics: dict,
    ) -> list[tuple[str, float]]:
        """Apply cost-aware routing mode to re-score or filter candidates."""
        mode = self._config.routing_mode

        if mode == ROUTING_BEST_QUALITY:
            return candidates

        if mode == ROUTING_BUDGET:
            return self._apply_budget_mode(candidates, all_metrics)

        if mode == ROUTING_BALANCED:
            return self._apply_balanced_mode(candidates, all_metrics)

        if mode == ROUTING_PARETO:
            return self._apply_pareto_mode(candidates, all_metrics)

        return candidates

    def _apply_budget_mode(
        self,
        candidates: list[tuple[str, float]],
        all_metrics: dict,
    ) -> list[tuple[str, float]]:
        """Filter to agents within budget; fall back to cheapest if all exceed cap."""
        cap = self._config.max_cost_per_task
        if cap is None:
            return candidates

        within_budget = [
            (ref, score)
            for ref, score in candidates
            if all_metrics[ref].avg_cost_per_task <= cap
        ]

        if within_budget:
            return within_budget

        # All exceed cap — return cheapest as sole candidate with zero score
        cheapest = min(candidates, key=lambda x: all_metrics[x[0]].avg_cost_per_task)
        return [(cheapest[0], 0.0)]

    def _apply_balanced_mode(
        self,
        candidates: list[tuple[str, float]],
        all_metrics: dict,
    ) -> list[tuple[str, float]]:
        """Re-score as weighted combo of quality and (1 - normalized_cost)."""
        costs = [all_metrics[ref].avg_cost_per_task for ref, _ in candidates]
        max_cost = max(costs) if costs else 0.0

        q_weight = self._config.cost_quality_tradeoff
        c_weight = 1.0 - q_weight

        result = []
        for ref, quality_score in candidates:
            cost = all_metrics[ref].avg_cost_per_task
            cost_score = 1.0 - (cost / max_cost) if max_cost > 0 else 1.0
            combined = q_weight * quality_score + c_weight * cost_score
            result.append((ref, min(1.0, max(0.0, combined))))
        return result

    def _apply_pareto_mode(
        self,
        candidates: list[tuple[str, float]],
        all_metrics: dict,
    ) -> list[tuple[str, float]]:
        """Keep only Pareto-optimal agents, then score by cost_quality_tradeoff."""
        frontier = self._get_pareto_frontier(candidates, all_metrics)

        costs = [all_metrics[ref].avg_cost_per_task for ref, _ in frontier]
        max_cost = max(costs) if costs else 0.0

        q_weight = self._config.cost_quality_tradeoff
        c_weight = 1.0 - q_weight

        result = []
        for ref, quality_score in frontier:
            cost = all_metrics[ref].avg_cost_per_task
            cost_score = 1.0 - (cost / max_cost) if max_cost > 0 else 1.0
            combined = q_weight * quality_score + c_weight * cost_score
            result.append((ref, min(1.0, max(0.0, combined))))
        return result

    def _get_pareto_frontier(
        self,
        candidates: list[tuple[str, float]],
        all_metrics: dict,
    ) -> list[tuple[str, float]]:
        """Return non-dominated agents (higher quality, lower cost = better)."""
        frontier = []
        for ref, quality in candidates:
            cost = all_metrics[ref].avg_cost_per_task
            dominated = any(
                other_quality >= quality and other_cost <= cost and (
                    other_quality > quality or other_cost < cost
                )
                for other_ref, other_quality in candidates
                if other_ref != ref
                for other_cost in [all_metrics[other_ref].avg_cost_per_task]
            )
            if not dominated:
                frontier.append((ref, quality))
        return frontier

    def _calculate_score(
        self,
        metrics: AgentPerformanceMetrics,
        task_type: str | None,
        complexity: int | None,
        profile: ModelProfile | None = None,
    ) -> float:
        """Calculate routing score for an agent.

        Profile adjustment: +10% for domain strengths, -10% for weaknesses.
        """
        config = self._config
        if metrics.bayesian_estimate is not None and metrics.total_tasks > 0:
            vc = min(metrics.variance_coefficient, 1.0)
            base_score = (
                metrics.bayesian_estimate.ci_lower
                * metrics.consistency_rate
                * (1.0 - vc)
            )
        else:
            base_score = metrics.variance_adjusted_reliability

        overall_component = base_score * config.overall_weight

        task_component = 0.0
        if task_type and task_type in metrics.success_by_task_type:
            task_rate = metrics.success_by_task_type[task_type]
            task_component = task_rate * config.task_type_weight
        else:
            task_component = base_score * 0.5 * config.task_type_weight

        complexity_component = 0.0
        if complexity and complexity in metrics.success_by_complexity:
            complexity_rate = metrics.success_by_complexity[complexity]
            complexity_component = complexity_rate * config.complexity_weight
        else:
            complexity_component = base_score * 0.5 * config.complexity_weight

        score = overall_component + task_component + complexity_component

        if profile and task_type:
            if task_type in profile.strengths:
                score *= 1.10
            elif task_type in profile.weaknesses:
                score *= 0.90

        return min(1.0, max(0.0, score))

    def _get_verdict(self, confidence: float) -> str:
        """Determine routing verdict based on confidence."""
        if confidence >= self._config.apply_threshold:
            return "APPLY"
        elif confidence >= self._config.ask_threshold:
            return "ASK_FIRST"
        else:
            return "SKIP"

    def _fallback_result(
        self,
        task_type: str | None,
        complexity: int | None,
    ) -> RoutingResult:
        """Create fallback result when no history available."""
        fallback = self._config.fallback_agent or "default-agent"
        return RoutingResult(
            selected_agent=fallback,
            confidence=0.0,
            verdict="ASK_FIRST",
            candidates=[],
            is_fallback=True,
            task_type=task_type,
            complexity=complexity,
        )

    def set_fallback_agent(self, agent_ref: str) -> None:
        """Set the fallback agent for when no history exists."""
        self._config.fallback_agent = agent_ref

    def invalidate_cache(self) -> None:
        """Force aggregator to refresh metrics from audit."""
        self._aggregator.invalidate_cache()
