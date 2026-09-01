"""Live entry point for AdaptiveBroker routing.

`ace tdd` and the MCP `build_feature` tool call `route_model()` before a TDD
cycle starts to pick which configured LLM among several candidates should run
it, instead of the caller always using one fixed client. Routing is driven
purely by the audit trail's `CYCLE_COMPLETED` history (see
`PerformanceAggregator`) -- with no prior runs it returns a transparent
fallback (the first candidate) and the caller proceeds unchanged.

The candidate refs are `"<provider>/<model>"` strings -- the same shape
`TDDCycleRunner` writes as the audit `actor_id` -- so a model's history lines
up with the ref used to route to it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.broker.adaptive_broker import AdaptiveBroker, BrokerConfig
from src.broker.performance_aggregator import PerformanceAggregator

logger = logging.getLogger(__name__)


@dataclass
class ModelRoutingDecision:
    """Outcome of routing one task among candidate models.

    `selected_model` is always one of `candidates`. `is_fallback` is True when
    the broker had no usable history for any candidate and the first candidate
    was chosen by default.
    """

    selected_model: str
    candidates: list[str]
    confidence: float
    verdict: str  # APPLY | ASK_FIRST | SKIP
    is_fallback: bool
    task_type: str | None = None
    scored_candidates: list[tuple[str, float]] = field(default_factory=list)
    reason: str = ""

    def to_payload(self) -> dict:
        """Audit / API-friendly dict (no content, only refs and scores)."""
        return {
            "selected_model": self.selected_model,
            "candidates": self.candidates,
            "confidence": round(self.confidence, 4),
            "verdict": self.verdict,
            "is_fallback": self.is_fallback,
            "task_type": self.task_type,
            "scored_candidates": [
                [ref, round(score, 4)] for ref, score in self.scored_candidates
            ],
            "reason": self.reason,
        }

    def summary_line(self) -> str:
        """One-line human summary for CLI output."""
        if len(self.candidates) < 2:
            return f"Model: {self.selected_model} (no routing — single candidate)"
        if self.is_fallback:
            return (
                f"Model: {self.selected_model} "
                f"(broker fallback — no audit history for {len(self.candidates)} candidates)"
            )
        others = ", ".join(
            f"{ref}={score:.2f}"
            for ref, score in self.scored_candidates
            if ref != self.selected_model
        )
        tail = f"; others: {others}" if others else ""
        return (
            f"Model: {self.selected_model} "
            f"(broker {self.verdict}, confidence {self.confidence:.2f}{tail})"
        )


def route_model(
    candidate_models: list[str],
    task_type: str | None,
    audit_database_url: str,
    *,
    fallback_model: str | None = None,
    broker_config: BrokerConfig | None = None,
) -> ModelRoutingDecision:
    """Pick the best model among `candidate_models` for a `task_type` task.

    Args:
        candidate_models: `"<provider>/<model>"` refs to choose between.
        task_type: task classifier the broker scores on (e.g. the language).
        audit_database_url: SQLAlchemy URL of the audit store to read history from.
        fallback_model: used when no candidate has history; defaults to the
            first candidate.
        broker_config: optional routing-mode / threshold overrides.

    Never raises on an unreachable or empty audit store -- it degrades to the
    fallback so a routing failure can't block a build.
    """
    if not candidate_models:
        raise ValueError("route_model() requires at least one candidate model")

    fallback = fallback_model or candidate_models[0]

    if len(candidate_models) == 1:
        return ModelRoutingDecision(
            selected_model=candidate_models[0],
            candidates=list(candidate_models),
            confidence=0.0,
            verdict="SKIP",
            is_fallback=True,
            task_type=task_type,
            reason="single candidate — nothing to route between",
        )

    try:
        from src.audit.store import AuditStore

        store = AuditStore(audit_database_url)
        store.create_tables()
        aggregator = PerformanceAggregator(store)
        broker = AdaptiveBroker(aggregator, broker_config)
        broker.set_fallback_agent(fallback)
        result = broker.route_task(task_type=task_type, allowed_agents=candidate_models)
    except Exception as exc:  # noqa: BLE001 -- routing must never block a build
        logger.warning("route_model: broker routing failed (%s) — using fallback", exc)
        return ModelRoutingDecision(
            selected_model=fallback,
            candidates=list(candidate_models),
            confidence=0.0,
            verdict="SKIP",
            is_fallback=True,
            task_type=task_type,
            reason=f"routing error: {exc}",
        )

    if result.is_fallback:
        selected = fallback if fallback in candidate_models else candidate_models[0]
        return ModelRoutingDecision(
            selected_model=selected,
            candidates=list(candidate_models),
            confidence=0.0,
            verdict=result.verdict,
            is_fallback=True,
            task_type=task_type,
            reason="no audit history for any candidate — first candidate chosen",
        )

    # route_task with allowed_agents guarantees selected_agent is in the set.
    scored = [
        (ref, score) for ref, score in result.candidates if ref in set(candidate_models)
    ]
    return ModelRoutingDecision(
        selected_model=result.selected_agent,
        candidates=list(candidate_models),
        confidence=result.confidence,
        verdict=result.verdict,
        is_fallback=False,
        task_type=task_type,
        scored_candidates=scored,
        reason=f"ranked on {task_type or 'overall'} history",
    )
