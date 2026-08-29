"""
TokenEfficiencyReporter — aggregates TokenUsage data from LanguagePods and
computes per-cycle token efficiency scores with optional cross-language comparison.

See ace_enterprise-k8t for acceptance criteria.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class TokenUsage:
    """Token consumption for one complete TDD cycle."""

    cycle_number: int
    input_tokens: int
    output_tokens: int
    # Model attribution, captured from the LLM client's generate() response
    # (see LanguagePod._intercept_tokens implementations). None for clients/
    # cycles that made no LLM call, or that predate this field.
    actual_model: str | None = None
    requested_model: str | None = None
    provider: str | None = None


@dataclass
class PodRun:
    """Input data for one pod's execution of a feature."""

    language: str
    feature_requirement: str
    token_usage: list[TokenUsage]
    cycles_to_green: int


@dataclass
class LanguageScore:
    """Token efficiency metrics for one language's run."""

    language: str
    feature_requirement: str
    total_input_tokens: int
    total_output_tokens: int
    cycles_to_green: int
    tokens_per_green: float

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "feature_requirement": self.feature_requirement,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "cycles_to_green": self.cycles_to_green,
            "tokens_per_green": self.tokens_per_green,
        }


@dataclass
class CrossLanguageComparison:
    """Comparison between two or more languages for the same feature."""

    feature_requirement: str
    scores: list[LanguageScore]
    most_efficient: str
    efficiency_ratio: float

    def to_dict(self) -> dict:
        return {
            "feature_requirement": self.feature_requirement,
            "scores": [s.to_dict() for s in self.scores],
            "most_efficient": self.most_efficient,
            "efficiency_ratio": self.efficiency_ratio,
        }


@dataclass
class EfficiencyReport:
    """Full token efficiency report, surfaced under the token_efficiency key."""

    scores: list[LanguageScore] = field(default_factory=list)
    comparison: CrossLanguageComparison | None = None

    def to_dict(self) -> dict:
        return {
            "token_efficiency": {
                "scores": [s.to_dict() for s in self.scores],
                "comparison": self.comparison.to_dict() if self.comparison else None,
            }
        }


class TokenEfficiencyReporter:
    """Computes token efficiency scores from LanguagePod run data."""

    @staticmethod
    def score(pod_runs: list[PodRun]) -> EfficiencyReport:
        scores = [_compute_score(run) for run in pod_runs]
        comparison = _build_comparison(scores)
        return EfficiencyReport(scores=scores, comparison=comparison)


# --- private helpers ---

def _compute_score(run: PodRun) -> LanguageScore:
    total_in = sum(u.input_tokens for u in run.token_usage)
    total_out = sum(u.output_tokens for u in run.token_usage)
    total = total_in + total_out
    tpg = total / run.cycles_to_green if run.cycles_to_green > 0 else math.inf
    return LanguageScore(
        language=run.language,
        feature_requirement=run.feature_requirement,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        cycles_to_green=run.cycles_to_green,
        tokens_per_green=tpg,
    )


def _build_comparison(scores: list[LanguageScore]) -> CrossLanguageComparison | None:
    from collections import defaultdict

    groups: dict[str, list[LanguageScore]] = defaultdict(list)
    for s in scores:
        groups[s.feature_requirement].append(s)

    multi = [(feat, ss) for feat, ss in groups.items() if len(ss) >= 2]
    if not multi:
        return None

    feat, group_scores = multi[0]
    most_efficient = min(group_scores, key=lambda s: s.tokens_per_green)
    least_efficient = max(group_scores, key=lambda s: s.tokens_per_green)
    ratio = (
        least_efficient.tokens_per_green / most_efficient.tokens_per_green
        if most_efficient.tokens_per_green > 0
        else 1.0
    )
    return CrossLanguageComparison(
        feature_requirement=feat,
        scores=group_scores,
        most_efficient=most_efficient.language,
        efficiency_ratio=ratio,
    )
