"""Tests for domain-specific evaluation rubrics (ace_enterprise-nf7)."""
from __future__ import annotations

import pytest

from src.benchmark.blind_evaluation import BlindEvaluator, EvaluationResult, Submission
from src.benchmark.rubrics import (
    AnalysisRubric,
    CodeGenerationRubric,
    DocumentationRubric,
    EvaluationRubric,
    RubricResult,
    ScoringDimension,
    TestWritingRubric,
    get_rubric,
)
from src.benchmark.rubrics.base import DimensionScore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GOOD_CODE = """\
def add(a: int, b: int) -> int:
    \"\"\"Add two integers.\"\"\"
    return a + b
"""

_BAD_SYNTAX = "def ??? broken syntax"

_GOOD_DOCS = """\
# Overview

This module provides utility functions.

## Usage

Call `add(1, 2)` to add numbers.

```python
result = add(1, 2)
print(result)
```

- Simple
- Efficient
"""

_GOOD_ANALYSIS = """\
## Introduction

This analysis examines performance characteristics.

## Findings

The results show significant improvement because the algorithm runs in O(n log n).
However, memory usage increases therefore we must balance speed and space.
Furthermore, the benchmarks confirm this trend.

## Conclusion

In conclusion, the approach is effective. The evidence supports this claim according to
benchmark data [Smith, 2024]. Therefore, we recommend adoption.
"""

_GOOD_TESTS = """\
def test_add_positive_numbers():
    assert add(1, 2) == 3

def test_add_with_zero():
    assert add(0, 5) == 5

def test_add_negative_numbers():
    assert add(-1, -2) == -3

def test_add_returns_none_when_invalid():
    assert add(None, 1) is None
"""


# ---------------------------------------------------------------------------
# Base class: ScoringDimension, DimensionScore, RubricResult
# ---------------------------------------------------------------------------

class TestScoringDimension:
    def test_fields_accessible(self):
        d = ScoringDimension("syntax", 0.3, "Valid syntax")
        assert d.name == "syntax"
        assert d.weight == pytest.approx(0.3)
        assert d.description == "Valid syntax"


class TestDimensionScore:
    def test_weighted_score(self):
        ds = DimensionScore(dimension="syntax", score=80.0, weight=0.5)
        assert ds.weighted_score == pytest.approx(40.0)

    def test_notes_optional(self):
        ds = DimensionScore(dimension="x", score=50.0, weight=0.5)
        assert ds.notes is None


class TestRubricResult:
    def test_fields_accessible(self):
        r = RubricResult(
            rubric_name="code",
            total_score=75.0,
            dimension_scores=[],
        )
        assert r.rubric_name == "code"
        assert r.total_score == pytest.approx(75.0)

    def test_total_score_bounded(self):
        # score() in base class clamps to [0, 100]
        r = RubricResult(rubric_name="x", total_score=150.0, dimension_scores=[])
        assert r.total_score == pytest.approx(150.0)  # raw value; clamping is in score()


# ---------------------------------------------------------------------------
# EvaluationRubric base
# ---------------------------------------------------------------------------

class TestEvaluationRubricBase:
    def test_subclass_without_name_raises(self):
        class BadRubric(EvaluationRubric):
            @property
            def dimensions(self):
                return []
            def _score_dimension(self, d, o, c):
                return 50.0

        with pytest.raises(NotImplementedError):
            BadRubric().name

    def test_score_aggregates_weighted_dimensions(self):
        class SimpleRubric(EvaluationRubric):
            @property
            def name(self):
                return "simple"
            @property
            def dimensions(self):
                return [
                    ScoringDimension("a", 0.6, ""),
                    ScoringDimension("b", 0.4, ""),
                ]
            def _score_dimension(self, d, o, c):
                return 100.0 if d == "a" else 50.0

        r = SimpleRubric().score("anything")
        assert r.total_score == pytest.approx(0.6 * 100.0 + 0.4 * 50.0)

    def test_score_clamps_above_100(self):
        class OverRubric(EvaluationRubric):
            @property
            def name(self):
                return "over"
            @property
            def dimensions(self):
                return [ScoringDimension("x", 1.0, "")]
            def _score_dimension(self, d, o, c):
                return 200.0  # raw over-score

        r = OverRubric().score("x")
        assert r.total_score == pytest.approx(100.0)

    def test_score_clamps_below_zero(self):
        class UnderRubric(EvaluationRubric):
            @property
            def name(self):
                return "under"
            @property
            def dimensions(self):
                return [ScoringDimension("x", 1.0, "")]
            def _score_dimension(self, d, o, c):
                return -50.0

        r = UnderRubric().score("x")
        assert r.total_score == pytest.approx(0.0)

    def test_result_contains_dimension_scores(self):
        class TwoRubric(EvaluationRubric):
            @property
            def name(self):
                return "two"
            @property
            def dimensions(self):
                return [ScoringDimension("p", 0.5, ""), ScoringDimension("q", 0.5, "")]
            def _score_dimension(self, d, o, c):
                return 60.0

        r = TwoRubric().score("x")
        assert len(r.dimension_scores) == 2


# ---------------------------------------------------------------------------
# get_rubric registry
# ---------------------------------------------------------------------------

class TestGetRubric:
    def test_code_returns_code_rubric(self):
        assert isinstance(get_rubric("code"), CodeGenerationRubric)

    def test_tests_returns_test_rubric(self):
        assert isinstance(get_rubric("tests"), TestWritingRubric)

    def test_test_alias(self):
        assert isinstance(get_rubric("test"), TestWritingRubric)

    def test_docs_returns_doc_rubric(self):
        assert isinstance(get_rubric("docs"), DocumentationRubric)

    def test_documentation_alias(self):
        assert isinstance(get_rubric("documentation"), DocumentationRubric)

    def test_analysis_returns_analysis_rubric(self):
        assert isinstance(get_rubric("analysis"), AnalysisRubric)

    def test_none_returns_none(self):
        assert get_rubric(None) is None

    def test_unknown_returns_none(self):
        assert get_rubric("unknown_type") is None

    def test_case_insensitive(self):
        assert get_rubric("CODE") is not None
        assert get_rubric("Code") is not None


# ---------------------------------------------------------------------------
# CodeGenerationRubric
# ---------------------------------------------------------------------------

class TestCodeGenerationRubric:
    def setup_method(self):
        self.rubric = CodeGenerationRubric()

    def test_name(self):
        assert self.rubric.name == "code_generation"

    def test_weights_sum_to_one(self):
        total = sum(d.weight for d in self.rubric.dimensions)
        assert total == pytest.approx(1.0)

    def test_good_code_scores_above_50(self):
        r = self.rubric.score(_GOOD_CODE)
        assert r.total_score > 50.0

    def test_bad_syntax_scores_zero_on_syntax(self):
        r = self.rubric.score(_BAD_SYNTAX)
        syntax_ds = next(ds for ds in r.dimension_scores if ds.dimension == "syntax")
        assert syntax_ds.score == pytest.approx(0.0)

    def test_good_code_passes_syntax(self):
        r = self.rubric.score(_GOOD_CODE)
        syntax_ds = next(ds for ds in r.dimension_scores if ds.dimension == "syntax")
        assert syntax_ds.score == pytest.approx(100.0)

    def test_security_penalised_for_eval(self):
        evil = "result = eval(user_input)"
        r = self.rubric.score(evil)
        sec_ds = next(ds for ds in r.dimension_scores if ds.dimension == "security")
        assert sec_ds.score == pytest.approx(0.0)

    def test_clean_code_passes_security(self):
        r = self.rubric.score(_GOOD_CODE)
        sec_ds = next(ds for ds in r.dimension_scores if ds.dimension == "security")
        assert sec_ds.score == pytest.approx(100.0)

    def test_no_test_content_gives_partial_tests_score(self):
        r = self.rubric.score(_GOOD_CODE, context={})
        tests_ds = next(ds for ds in r.dimension_scores if ds.dimension == "tests")
        assert tests_ds.score == pytest.approx(50.0)  # partial credit for valid code

    def test_bad_syntax_no_test_credit(self):
        r = self.rubric.score(_BAD_SYNTAX, context={})
        tests_ds = next(ds for ds in r.dimension_scores if ds.dimension == "tests")
        assert tests_ds.score == pytest.approx(0.0)

    def test_rubric_name_in_result(self):
        r = self.rubric.score(_GOOD_CODE)
        assert r.rubric_name == "code_generation"


# ---------------------------------------------------------------------------
# DocumentationRubric
# ---------------------------------------------------------------------------

class TestDocumentationRubric:
    def setup_method(self):
        self.rubric = DocumentationRubric()

    def test_name(self):
        assert self.rubric.name == "documentation"

    def test_weights_sum_to_one(self):
        assert sum(d.weight for d in self.rubric.dimensions) == pytest.approx(1.0)

    def test_good_docs_score_above_50(self):
        r = self.rubric.score(_GOOD_DOCS)
        assert r.total_score > 50.0

    def test_empty_string_low_score(self):
        r = self.rubric.score("")
        assert r.total_score < 30.0

    def test_code_block_detected(self):
        r = self.rubric.score(_GOOD_DOCS)
        ex_ds = next(ds for ds in r.dimension_scores if ds.dimension == "examples")
        assert ex_ds.score > 0.0

    def test_no_code_block_zero_examples(self):
        r = self.rubric.score("Just prose, no code blocks at all.")
        ex_ds = next(ds for ds in r.dimension_scores if ds.dimension == "examples")
        assert ex_ds.score == pytest.approx(0.0)

    def test_markdown_bullet_list_detected(self):
        r = self.rubric.score(_GOOD_DOCS)
        fmt_ds = next(ds for ds in r.dimension_scores if ds.dimension == "formatting")
        assert fmt_ds.score > 0.0

    def test_heading_detected(self):
        r = self.rubric.score(_GOOD_DOCS)
        fmt_ds = next(ds for ds in r.dimension_scores if ds.dimension == "formatting")
        assert fmt_ds.score == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# AnalysisRubric
# ---------------------------------------------------------------------------

class TestAnalysisRubric:
    def setup_method(self):
        self.rubric = AnalysisRubric()

    def test_name(self):
        assert self.rubric.name == "analysis"

    def test_weights_sum_to_one(self):
        assert sum(d.weight for d in self.rubric.dimensions) == pytest.approx(1.0)

    def test_good_analysis_scores_above_50(self):
        r = self.rubric.score(_GOOD_ANALYSIS)
        assert r.total_score > 50.0

    def test_reasoning_words_detected(self):
        r = self.rubric.score(_GOOD_ANALYSIS)
        reason_ds = next(ds for ds in r.dimension_scores if ds.dimension == "reasoning")
        assert reason_ds.score > 0.0

    def test_no_reasoning_words_zero_reasoning(self):
        r = self.rubric.score("This is a statement. Another statement.")
        reason_ds = next(ds for ds in r.dimension_scores if ds.dimension == "reasoning")
        assert reason_ds.score == pytest.approx(0.0)

    def test_citation_detected(self):
        r = self.rubric.score(_GOOD_ANALYSIS)
        cite_ds = next(ds for ds in r.dimension_scores if ds.dimension == "citations")
        assert cite_ds.score == pytest.approx(100.0)

    def test_no_citation_zero_score(self):
        r = self.rubric.score("Just conclusions without any references.")
        cite_ds = next(ds for ds in r.dimension_scores if ds.dimension == "citations")
        assert cite_ds.score == pytest.approx(0.0)

    def test_url_counts_as_citation(self):
        r = self.rubric.score("See https://example.com for details.")
        cite_ds = next(ds for ds in r.dimension_scores if ds.dimension == "citations")
        assert cite_ds.score == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# TestWritingRubric
# ---------------------------------------------------------------------------

class TestTestWritingRubric:
    def setup_method(self):
        self.rubric = TestWritingRubric()

    def test_name(self):
        assert self.rubric.name == "test_writing"

    def test_weights_sum_to_one(self):
        assert sum(d.weight for d in self.rubric.dimensions) == pytest.approx(1.0)

    def test_good_tests_score_above_50(self):
        r = self.rubric.score(_GOOD_TESTS)
        assert r.total_score > 50.0

    def test_bad_syntax_low_score(self):
        r = self.rubric.score(_BAD_SYNTAX)
        assert r.total_score < 40.0

    def test_none_edge_case_detected(self):
        code = "def test_handles_none():\n    assert fn(None) == 0"
        r = self.rubric.score(code)
        edge_ds = next(ds for ds in r.dimension_scores if ds.dimension == "edge_cases")
        assert edge_ds.score > 0.0

    def test_no_edge_cases_zero(self):
        code = "def test_basic():\n    assert fn(5) == 10"
        r = self.rubric.score(code)
        edge_ds = next(ds for ds in r.dimension_scores if ds.dimension == "edge_cases")
        assert edge_ds.score == pytest.approx(0.0)

    def test_multiple_asserts_improve_assertion_score(self):
        many = "\n".join(
            f"def test_case_{i}():\n    assert fn({i}) == {i*2}\n    assert fn({i}) >= 0"
            for i in range(3)
        )
        r = self.rubric.score(many)
        assert_ds = next(ds for ds in r.dimension_scores if ds.dimension == "assertions")
        assert assert_ds.score > 0.0

    def test_descriptive_names_improve_naming_score(self):
        code = "def test_add_with_zero_value():\n    assert add(0, 5) == 5"
        r = self.rubric.score(code)
        name_ds = next(ds for ds in r.dimension_scores if ds.dimension == "naming")
        assert name_ds.score == pytest.approx(100.0)

    def test_terse_name_lower_naming_score(self):
        code = "def test_x():\n    assert True"
        r = self.rubric.score(code)
        name_ds = next(ds for ds in r.dimension_scores if ds.dimension == "naming")
        assert name_ds.score < 100.0

    def test_five_plus_tests_full_coverage_score(self):
        code = "\n".join(
            f"def test_case_{i}():\n    assert True" for i in range(5)
        )
        r = self.rubric.score(code)
        cov_ds = next(ds for ds in r.dimension_scores if ds.dimension == "coverage")
        assert cov_ds.score == pytest.approx(100.0)

    def test_no_tests_zero_coverage(self):
        r = self.rubric.score("def helper(): pass")
        cov_ds = next(ds for ds in r.dimension_scores if ds.dimension == "coverage")
        assert cov_ds.score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# BlindEvaluator rubric integration
# ---------------------------------------------------------------------------

class TestBlindEvaluatorRubricIntegration:
    def _sub(self, output_type="code", content=_GOOD_CODE):
        return Submission(
            task_id="t1", submission_id="s1",
            output_type=output_type, output_content=content,
        )

    def test_rubric_name_set_for_known_type(self):
        ev = BlindEvaluator()
        result = ev.evaluate(self._sub(output_type="code"))
        assert result.rubric_name == "code_generation"

    def test_rubric_name_none_for_unknown_type(self):
        ev = BlindEvaluator()
        result = ev.evaluate(self._sub(output_type="unknown"))
        assert result.rubric_name is None

    def test_docs_type_uses_docs_rubric(self):
        ev = BlindEvaluator()
        result = ev.evaluate(self._sub(output_type="docs", content=_GOOD_DOCS))
        assert result.rubric_name == "documentation"

    def test_analysis_type_uses_analysis_rubric(self):
        ev = BlindEvaluator()
        result = ev.evaluate(self._sub(output_type="analysis", content=_GOOD_ANALYSIS))
        assert result.rubric_name == "analysis"

    def test_tests_type_uses_test_rubric(self):
        ev = BlindEvaluator()
        result = ev.evaluate(self._sub(output_type="tests", content=_GOOD_TESTS))
        assert result.rubric_name == "test_writing"

    def test_rubric_result_score_in_range(self):
        ev = BlindEvaluator()
        result = ev.evaluate(self._sub(output_type="code"))
        assert 0 <= result.quality_score <= 100

    def test_rubric_dimensions_in_details(self):
        ev = BlindEvaluator()
        result = ev.evaluate(self._sub(output_type="code"))
        assert "rubric_dimensions" in result.details

    def test_fallback_path_has_no_rubric_name(self):
        ev = BlindEvaluator()
        result = ev.evaluate(self._sub(output_type="other"))
        assert result.rubric_name is None

    def test_fallback_path_still_scores(self):
        ev = BlindEvaluator()
        result = ev.evaluate(self._sub(output_type="other", content=_GOOD_CODE))
        assert result.quality_score > 0

    def test_result_is_evaluation_result(self):
        ev = BlindEvaluator()
        assert isinstance(ev.evaluate(self._sub()), EvaluationResult)
