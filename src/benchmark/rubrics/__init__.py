"""Domain-specific evaluation rubrics.

Bead: ace_enterprise-nf7
"""

from src.benchmark.rubrics.analysis import AnalysisRubric
from src.benchmark.rubrics.base import (
    DimensionScore,
    EvaluationRubric,
    RubricResult,
    ScoringDimension,
)
from src.benchmark.rubrics.code import CodeGenerationRubric
from src.benchmark.rubrics.docs import DocumentationRubric
from src.benchmark.rubrics.tests import TestWritingRubric

_REGISTRY: dict[str, EvaluationRubric] = {
    "code": CodeGenerationRubric(),
    "tests": TestWritingRubric(),
    "test": TestWritingRubric(),
    "docs": DocumentationRubric(),
    "documentation": DocumentationRubric(),
    "analysis": AnalysisRubric(),
}


def get_rubric(task_type: str | None) -> EvaluationRubric | None:
    """Return the rubric for *task_type*, or None if no match."""
    if task_type is None:
        return None
    return _REGISTRY.get(task_type.lower())


__all__ = [
    "ScoringDimension",
    "DimensionScore",
    "RubricResult",
    "EvaluationRubric",
    "CodeGenerationRubric",
    "DocumentationRubric",
    "AnalysisRubric",
    "TestWritingRubric",
    "get_rubric",
]
