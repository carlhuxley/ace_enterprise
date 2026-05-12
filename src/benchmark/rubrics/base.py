"""Base classes for domain-specific evaluation rubrics.

Bead: ace_enterprise-nf7
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScoringDimension:
    """One measurable axis within a rubric."""

    name: str
    weight: float    # fraction of total score; all weights in a rubric must sum to 1.0
    description: str


@dataclass
class DimensionScore:
    """Score awarded on a single dimension."""

    dimension: str
    score: float     # 0-100
    weight: float
    notes: str | None = None

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class RubricResult:
    """Aggregated result from running a rubric over one output."""

    rubric_name: str
    total_score: float            # 0-100 weighted sum across dimensions
    dimension_scores: list[DimensionScore]
    details: dict = field(default_factory=dict)


class EvaluationRubric:
    """Abstract base: domain-specific scoring rubric.

    Subclasses define `name`, `dimensions`, and `_score_dimension`.
    `score()` orchestrates the loop and aggregates the weighted total.
    """

    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def dimensions(self) -> list[ScoringDimension]:
        raise NotImplementedError

    def score(self, output: str, context: dict | None = None) -> RubricResult:
        """Evaluate *output* and return a RubricResult.

        Args:
            output:  The raw text/code to evaluate.
            context: Optional metadata dict (e.g. ``{"test_content": "..."}``).
        """
        ctx = context or {}
        dimension_scores = []
        for dim in self.dimensions:
            raw = self._score_dimension(dim.name, output, ctx)
            raw = max(0.0, min(100.0, raw))
            dimension_scores.append(
                DimensionScore(dimension=dim.name, score=raw, weight=dim.weight)
            )
        total = sum(ds.weighted_score for ds in dimension_scores)
        return RubricResult(
            rubric_name=self.name,
            total_score=min(100.0, max(0.0, total)),
            dimension_scores=dimension_scores,
        )

    def _score_dimension(self, dimension: str, output: str, context: dict) -> float:
        """Return a 0-100 score for the named dimension.  Must be overridden."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement _score_dimension")
