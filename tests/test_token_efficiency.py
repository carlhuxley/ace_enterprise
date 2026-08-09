"""Tests for TokenEfficiencyReporter (ace_enterprise-k8t)."""
from src.agents.language_pod import TokenUsage
from src.analytics.token_efficiency import (
    CrossLanguageComparison,
    EfficiencyReport,
    LanguageScore,
    PodRun,
    TokenEfficiencyReporter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _usage(cycle: int, input_tokens: int, output_tokens: int = 0):
    return TokenUsage(cycle_number=cycle, input_tokens=input_tokens, output_tokens=output_tokens)


def _python_run(feature="Auth feature", cycles=1, tokens_per_cycle=200):
    usage = [_usage(c + 1, tokens_per_cycle) for c in range(cycles)]
    return PodRun(
        language="python",
        feature_requirement=feature,
        token_usage=usage,
        cycles_to_green=cycles,
    )


def _go_run(feature="Auth feature", cycles=2, tokens_per_cycle=150):
    usage = [_usage(c + 1, tokens_per_cycle) for c in range(cycles)]
    return PodRun(
        language="go",
        feature_requirement=feature,
        token_usage=usage,
        cycles_to_green=cycles,
    )


# ---------------------------------------------------------------------------
# PodRun schema
# ---------------------------------------------------------------------------

class TestPodRun:
    def test_fields(self):
        run = PodRun(
            language="python",
            feature_requirement="Process an order",
            token_usage=[_usage(1, 100)],
            cycles_to_green=1,
        )
        assert run.language == "python"
        assert run.feature_requirement == "Process an order"
        assert run.cycles_to_green == 1
        assert len(run.token_usage) == 1


# ---------------------------------------------------------------------------
# LanguageScore schema
# ---------------------------------------------------------------------------

class TestLanguageScore:
    def test_fields(self):
        score = LanguageScore(
            language="go",
            feature_requirement="Process an order",
            total_input_tokens=400,
            total_output_tokens=0,
            cycles_to_green=2,
            tokens_per_green=200.0,
        )
        assert score.language == "go"
        assert score.tokens_per_green == 200.0


# ---------------------------------------------------------------------------
# EfficiencyReport.score — single language
# ---------------------------------------------------------------------------

class TestScoreSingleLanguage:
    def test_returns_efficiency_report(self):
        report = TokenEfficiencyReporter.score([_python_run()])
        assert isinstance(report, EfficiencyReport)

    def test_score_contains_one_language_score(self):
        report = TokenEfficiencyReporter.score([_python_run()])
        assert len(report.scores) == 1

    def test_language_score_has_correct_language(self):
        report = TokenEfficiencyReporter.score([_python_run()])
        assert report.scores[0].language == "python"

    def test_total_input_tokens_summed(self):
        run = PodRun(
            language="python",
            feature_requirement="feat",
            token_usage=[_usage(1, 100), _usage(2, 150)],
            cycles_to_green=2,
        )
        report = TokenEfficiencyReporter.score([run])
        assert report.scores[0].total_input_tokens == 250

    def test_total_output_tokens_summed(self):
        run = PodRun(
            language="python",
            feature_requirement="feat",
            token_usage=[_usage(1, 100, 50), _usage(2, 150, 80)],
            cycles_to_green=2,
        )
        report = TokenEfficiencyReporter.score([run])
        assert report.scores[0].total_output_tokens == 130

    def test_cycles_to_green_preserved(self):
        run = _python_run(cycles=3)
        report = TokenEfficiencyReporter.score([run])
        assert report.scores[0].cycles_to_green == 3

    def test_tokens_per_green_is_total_over_cycles(self):
        run = PodRun(
            language="python",
            feature_requirement="feat",
            token_usage=[_usage(1, 300), _usage(2, 300)],
            cycles_to_green=2,
        )
        report = TokenEfficiencyReporter.score([run])
        # total = 600, cycles = 2 → 300.0
        assert report.scores[0].tokens_per_green == 300.0

    def test_no_comparison_for_single_language(self):
        report = TokenEfficiencyReporter.score([_python_run()])
        assert report.comparison is None

    def test_empty_pod_runs_returns_empty_report(self):
        report = TokenEfficiencyReporter.score([])
        assert report.scores == []
        assert report.comparison is None

    def test_zero_cycles_to_green_yields_inf_tokens_per_green(self):
        run = PodRun(
            language="python",
            feature_requirement="feat",
            token_usage=[_usage(1, 100)],
            cycles_to_green=0,
        )
        import math
        report = TokenEfficiencyReporter.score([run])
        assert math.isinf(report.scores[0].tokens_per_green)


# ---------------------------------------------------------------------------
# Cross-language comparison
# ---------------------------------------------------------------------------

class TestCrossLanguageComparison:
    def test_comparison_present_when_two_languages_same_feature(self):
        report = TokenEfficiencyReporter.score([_python_run(), _go_run()])
        assert report.comparison is not None

    def test_comparison_is_correct_type(self):
        report = TokenEfficiencyReporter.score([_python_run(), _go_run()])
        assert isinstance(report.comparison, CrossLanguageComparison)

    def test_comparison_contains_two_scores(self):
        report = TokenEfficiencyReporter.score([_python_run(), _go_run()])
        assert len(report.comparison.scores) == 2

    def test_most_efficient_is_lower_tokens_per_green(self):
        python = PodRun(
            language="python",
            feature_requirement="feat",
            token_usage=[_usage(1, 100)],
            cycles_to_green=1,  # 100 tokens/green
        )
        go = PodRun(
            language="go",
            feature_requirement="feat",
            token_usage=[_usage(1, 50)],
            cycles_to_green=1,  # 50 tokens/green
        )
        report = TokenEfficiencyReporter.score([python, go])
        assert report.comparison.most_efficient == "go"

    def test_efficiency_ratio_is_least_over_most(self):
        python = PodRun(
            language="python",
            feature_requirement="feat",
            token_usage=[_usage(1, 400)],
            cycles_to_green=1,  # 400 t/g
        )
        go = PodRun(
            language="go",
            feature_requirement="feat",
            token_usage=[_usage(1, 100)],
            cycles_to_green=1,  # 100 t/g
        )
        report = TokenEfficiencyReporter.score([python, go])
        assert report.comparison.efficiency_ratio == pytest.approx(4.0)

    def test_no_comparison_for_different_features(self):
        python = _python_run(feature="Feature A")
        go = _go_run(feature="Feature B")
        report = TokenEfficiencyReporter.score([python, go])
        assert report.comparison is None

    def test_comparison_feature_requirement_matches(self):
        report = TokenEfficiencyReporter.score([_python_run(), _go_run()])
        assert report.comparison.feature_requirement == "Auth feature"


# ---------------------------------------------------------------------------
# to_dict — experiment log surfacing
# ---------------------------------------------------------------------------

class TestToDict:
    def test_to_dict_returns_dict(self):
        report = TokenEfficiencyReporter.score([_python_run()])
        assert isinstance(report.to_dict(), dict)

    def test_to_dict_has_token_efficiency_key(self):
        report = TokenEfficiencyReporter.score([_python_run()])
        assert "token_efficiency" in report.to_dict()

    def test_to_dict_scores_list_present(self):
        report = TokenEfficiencyReporter.score([_python_run(), _go_run()])
        data = report.to_dict()["token_efficiency"]
        assert "scores" in data
        assert len(data["scores"]) == 2

    def test_to_dict_score_contains_required_fields(self):
        report = TokenEfficiencyReporter.score([_python_run()])
        score_dict = report.to_dict()["token_efficiency"]["scores"][0]
        assert "language" in score_dict
        assert "total_input_tokens" in score_dict
        assert "total_output_tokens" in score_dict
        assert "cycles_to_green" in score_dict
        assert "tokens_per_green" in score_dict

    def test_to_dict_comparison_none_when_single_language(self):
        report = TokenEfficiencyReporter.score([_python_run()])
        assert report.to_dict()["token_efficiency"]["comparison"] is None

    def test_to_dict_comparison_present_when_two_languages(self):
        report = TokenEfficiencyReporter.score([_python_run(), _go_run()])
        comparison = report.to_dict()["token_efficiency"]["comparison"]
        assert comparison is not None
        assert "most_efficient" in comparison
        assert "efficiency_ratio" in comparison


# ---------------------------------------------------------------------------
# Integration: stub pods with known token counts
# ---------------------------------------------------------------------------

import pytest


class TestIntegrationWithStubPods:
    def test_two_pod_stubs_produce_correct_report(self, tmp_path):
        from unittest.mock import MagicMock
        from src.agents.language_pod import PhaseResult, PodSpec, TokenUsage
        from src.agents.python_language_pod import PythonLanguagePod
        from src.agents.go_language_pod import GoLanguagePod
        from unittest.mock import patch

        # Python stub pod (current architecture: worker + orchestrator)
        worker = MagicMock()
        worker.llm_client = MagicMock()
        worker.llm_client.generate.return_value = {
            "content": "def test_foo(): pass",
            "prompt_tokens": 200,
            "completion_tokens": 0,
            "tokens_used": 200,
            "latency_ms": 10,
            "model": "gpt-4o",
        }

        # Make generate_test simulate the real worker calling llm_client.generate
        def _generate_test_calls_llm(*args, **kwargs):
            worker.llm_client.generate("test prompt")
            return "def test_foo(): pass"

        worker.generate_test.side_effect = _generate_test_calls_llm

        orchestrator = MagicMock()
        orchestrator.pulse.return_value = PhaseResult(passed=False, output="1 failed", error=None)

        py_pod = PythonLanguagePod(worker, tmp_path, orchestrator)

        spec = PodSpec(
            feature_requirement="Auth feature",
            test_file=tmp_path / "test_auth.py",
            implementation_file=tmp_path / "auth.py",
            cycle_number=1,
        )

        py_pod.run_red(spec)

        py_run = PodRun(
            language="python",
            feature_requirement=spec.feature_requirement,
            token_usage=py_pod.token_usage(),
            cycles_to_green=1,
        )

        # Go stub pod
        go_client = MagicMock()
        go_client.generate.return_value = {
            "content": "package main\nfunc main() {}",
            "tokens_used": 100,
            "latency_ms": 10,
            "model": "gpt-4o",
        }
        go_pod = GoLanguagePod(llm_client=go_client)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="FAIL", stderr="")
            go_pod.run_red(spec)

        go_run = PodRun(
            language="go",
            feature_requirement=spec.feature_requirement,
            token_usage=go_pod.token_usage(),
            cycles_to_green=1,
        )

        report = TokenEfficiencyReporter.score([py_run, go_run])

        assert len(report.scores) == 2
        py_score = next(s for s in report.scores if s.language == "python")
        go_score = next(s for s in report.scores if s.language == "go")
        assert py_score.total_input_tokens == 200
        assert go_score.total_input_tokens == 100
        assert report.comparison is not None
        assert report.comparison.most_efficient == "go"
