"""TestWritingRubric — evaluates test suite output.

Dimensions (weights sum to 1.0):
  edge_cases  0.30  boundary conditions tested (None, empty, 0, negative)
  assertions  0.30  meaningful assert statements relative to test count
  naming      0.20  descriptive test function names
  coverage    0.20  multiple independent test functions

Bead: ace_enterprise-nf7
"""

from __future__ import annotations

import ast
import re

from src.benchmark.rubrics.base import EvaluationRubric, ScoringDimension

_EDGE_PATTERNS = (
    r"\bNone\b", r"\[\]", r"\{\}", r'""', r"''",
    r"\b0\b", r"-1", r"empty", r"boundary", r"invalid",
    r"negative", r"overflow", r"zero",
)


class TestWritingRubric(EvaluationRubric):
    @property
    def name(self) -> str:
        return "test_writing"

    @property
    def dimensions(self) -> list[ScoringDimension]:
        return [
            ScoringDimension("edge_cases", 0.30, "Boundary conditions tested"),
            ScoringDimension("assertions", 0.30, "Assert density relative to test count"),
            ScoringDimension("naming",     0.20, "Descriptive test function names"),
            ScoringDimension("coverage",   0.20, "Multiple independent test functions"),
        ]

    def _score_dimension(self, dimension: str, output: str, context: dict) -> float:
        if dimension == "edge_cases":
            return self._score_edge_cases(output)
        if dimension == "assertions":
            return self._score_assertions(output)
        if dimension == "naming":
            return self._score_naming(output)
        if dimension == "coverage":
            return self._score_coverage(output)
        return 0.0

    # ------------------------------------------------------------------

    def _score_edge_cases(self, code: str) -> float:
        found = sum(1 for p in _EDGE_PATTERNS if re.search(p, code))
        return min(100.0, found * 20.0)

    def _score_assertions(self, code: str) -> float:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return 0.0
        test_fns = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test")
        ]
        if not test_fns:
            return 0.0
        assert_count = sum(
            1 for n in ast.walk(tree) if isinstance(n, ast.Assert)
        )
        ratio = assert_count / len(test_fns)
        return min(100.0, ratio * 50.0)

    def _score_naming(self, code: str) -> float:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return 0.0
        test_fns = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test")
        ]
        if not test_fns:
            return 0.0
        # Descriptive = name has more than one word part after "test_"
        descriptive = sum(1 for n in test_fns if len(n.split("_")) >= 3)
        return (descriptive / len(test_fns)) * 100.0

    def _score_coverage(self, code: str) -> float:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return 0.0
        test_fns = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test")
        ]
        count = len(test_fns)
        if count == 0:
            return 0.0
        if count == 1:
            return 40.0
        if count == 2:
            return 60.0
        if count <= 4:
            return 80.0
        return 100.0
