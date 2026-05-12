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


@dataclass
class BrokerConfig:
    """Configuration for AdaptiveBroker."""

    apply_threshold: float = 0.70
    ask_threshold: float = 0.35
    task_type_weight: float = 0.3
    complexity_weight: float = 0.3
    overall_weight: float = 0.4
    fallback_agent: str | None = None


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
    ) -> RoutingResult:
        """Route task to best agent based on performance history."""
        all_metrics = self._aggregator.get_all_agent_metrics()

        if not all_metrics:
            return self._fallback_result(task_type, complexity)

        profiles = self._aggregator.get_all_model_profiles()

        candidates = []
        for agent_ref, metrics in all_metrics.items():
            profile = profiles.get(agent_ref)
            score = self._calculate_score(metrics, task_type, complexity, profile)
            candidates.append((agent_ref, score))

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
        base_score = metrics.reliability_score

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
