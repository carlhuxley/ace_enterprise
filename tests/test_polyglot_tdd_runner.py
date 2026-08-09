"""Tests for PolyglotTDDRunner (ace_enterprise-bz8)."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.agents.language_pod import PhaseResult, PodSpec, TokenUsage
from src.analytics.token_efficiency import EfficiencyReport
from src.agents.polyglot_tdd_runner import (
    PodFactory,
    PolyglotRunResult,
    PolyglotTDDRunner,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _passing() -> PhaseResult:
    return PhaseResult(passed=True, output="ok")


def _failing() -> PhaseResult:
    return PhaseResult(passed=False, output="FAIL", error="AssertionError")


def _stub_pod(
    red_result=None,
    green_results=None,
    refactor_result=None,
    tokens_per_phase=100,
):
    """Return a MagicMock that satisfies the LanguagePod protocol."""
    pod = MagicMock()
    pod.run_red.return_value = red_result or _failing()
    if green_results is None:
        pod.run_green.return_value = _passing()
    else:
        pod.run_green.side_effect = green_results
    pod.run_refactor.return_value = refactor_result or _passing()
    pod.token_usage.return_value = [
        TokenUsage(cycle_number=1, input_tokens=tokens_per_phase, output_tokens=0)
    ]
    return pod


def _factory(pods: dict):
    """Return a PodFactory stub that maps language → pod."""
    factory = MagicMock()
    factory.create.side_effect = lambda lang, **kw: pods[lang]
    return factory


def _run(runner, feature="Auth feature", languages=("python",), tmp_path=None):
    p = Path(tmp_path) if tmp_path else Path("/tmp/test_run")
    return runner.run(
        feature_requirement=feature,
        test_file=p / "test_auth.py",
        implementation_file=p / "auth.py",
        languages=list(languages),
    )


# ---------------------------------------------------------------------------
# PolyglotRunResult schema
# ---------------------------------------------------------------------------

class TestPolyglotRunResult:
    def test_has_language_results(self, tmp_path):
        pod = _stub_pod()
        runner = PolyglotTDDRunner(_factory({"python": pod}))
        result = _run(runner, languages=["python"], tmp_path=tmp_path)
        assert hasattr(result, "language_results")

    def test_has_efficiency_report(self, tmp_path):
        pod = _stub_pod()
        runner = PolyglotTDDRunner(_factory({"python": pod}))
        result = _run(runner, languages=["python"], tmp_path=tmp_path)
        assert hasattr(result, "efficiency_report")
        assert isinstance(result.efficiency_report, EfficiencyReport)


# ---------------------------------------------------------------------------
# Single-language run
# ---------------------------------------------------------------------------

class TestSingleLanguageRun:
    def test_returns_polyglot_run_result(self, tmp_path):
        pod = _stub_pod()
        runner = PolyglotTDDRunner(_factory({"python": pod}))
        result = _run(runner, languages=["python"], tmp_path=tmp_path)
        assert isinstance(result, PolyglotRunResult)

    def test_all_three_phases_called(self, tmp_path):
        pod = _stub_pod()
        runner = PolyglotTDDRunner(_factory({"python": pod}))
        _run(runner, languages=["python"], tmp_path=tmp_path)
        pod.run_red.assert_called_once()
        pod.run_green.assert_called()
        pod.run_refactor.assert_called_once()

    def test_language_results_contains_language_key(self, tmp_path):
        pod = _stub_pod()
        runner = PolyglotTDDRunner(_factory({"python": pod}))
        result = _run(runner, languages=["python"], tmp_path=tmp_path)
        assert "python" in result.language_results

    def test_efficiency_report_has_one_score(self, tmp_path):
        pod = _stub_pod()
        runner = PolyglotTDDRunner(_factory({"python": pod}))
        result = _run(runner, languages=["python"], tmp_path=tmp_path)
        assert len(result.efficiency_report.scores) == 1

    def test_efficiency_report_no_comparison_for_one_language(self, tmp_path):
        pod = _stub_pod()
        runner = PolyglotTDDRunner(_factory({"python": pod}))
        result = _run(runner, languages=["python"], tmp_path=tmp_path)
        assert result.efficiency_report.comparison is None

    def test_cycles_to_green_is_one_on_first_pass(self, tmp_path):
        pod = _stub_pod(green_results=[_passing()])
        runner = PolyglotTDDRunner(_factory({"python": pod}))
        result = _run(runner, languages=["python"], tmp_path=tmp_path)
        score = result.efficiency_report.scores[0]
        assert score.cycles_to_green == 1

    def test_cycles_to_green_increments_on_retry(self, tmp_path):
        pod = _stub_pod(green_results=[_failing(), _failing(), _passing()])
        runner = PolyglotTDDRunner(_factory({"python": pod}))
        result = _run(runner, languages=["python"], tmp_path=tmp_path)
        score = result.efficiency_report.scores[0]
        assert score.cycles_to_green == 3

    def test_green_retry_does_not_exceed_max_cycles(self, tmp_path):
        always_failing = [_failing()] * 10
        pod = _stub_pod(green_results=always_failing)
        runner = PolyglotTDDRunner(_factory({"python": pod}), max_cycles=3)
        _run(runner, languages=["python"], tmp_path=tmp_path)
        assert pod.run_green.call_count == 3


# ---------------------------------------------------------------------------
# Dual-language run
# ---------------------------------------------------------------------------

class TestDualLanguageRun:
    def test_returns_result_with_both_languages(self, tmp_path):
        py_pod = _stub_pod(tokens_per_phase=200)
        go_pod = _stub_pod(tokens_per_phase=100)
        runner = PolyglotTDDRunner(_factory({"python": py_pod, "go": go_pod}))
        result = _run(runner, languages=["python", "go"], tmp_path=tmp_path)
        assert "python" in result.language_results
        assert "go" in result.language_results

    def test_efficiency_report_has_two_scores(self, tmp_path):
        py_pod = _stub_pod(tokens_per_phase=200)
        go_pod = _stub_pod(tokens_per_phase=100)
        runner = PolyglotTDDRunner(_factory({"python": py_pod, "go": go_pod}))
        result = _run(runner, languages=["python", "go"], tmp_path=tmp_path)
        assert len(result.efficiency_report.scores) == 2

    def test_comparison_present_for_two_languages(self, tmp_path):
        py_pod = _stub_pod(tokens_per_phase=200)
        go_pod = _stub_pod(tokens_per_phase=100)
        runner = PolyglotTDDRunner(_factory({"python": py_pod, "go": go_pod}))
        result = _run(runner, languages=["python", "go"], tmp_path=tmp_path)
        assert result.efficiency_report.comparison is not None

    def test_more_efficient_language_identified(self, tmp_path):
        py_pod = _stub_pod(tokens_per_phase=200)
        go_pod = _stub_pod(tokens_per_phase=100)
        runner = PolyglotTDDRunner(_factory({"python": py_pod, "go": go_pod}))
        result = _run(runner, languages=["python", "go"], tmp_path=tmp_path)
        assert result.efficiency_report.comparison.most_efficient == "go"

    def test_one_language_failure_does_not_abort_other(self, tmp_path):
        py_pod = _stub_pod(green_results=[_failing()] * 5)  # never passes
        go_pod = _stub_pod()
        runner = PolyglotTDDRunner(_factory({"python": py_pod, "go": go_pod}), max_cycles=2)
        result = _run(runner, languages=["python", "go"], tmp_path=tmp_path)
        # Go should still complete even though Python never went green
        assert "go" in result.language_results
        go_pod.run_refactor.assert_called_once()


# ---------------------------------------------------------------------------
# PodFactory
# ---------------------------------------------------------------------------

class TestPodFactory:
    def test_create_python_returns_python_pod(self, tmp_path):
        from src.agents.python_language_pod import PythonLanguagePod
        worker = MagicMock()
        worker.llm_client = MagicMock()
        worker.llm_client.generate.return_value = {
            "content": "", "tokens_used": 0, "latency_ms": 0, "model": "gpt-4o"
        }
        pod = PodFactory.create(
            "python", worker=worker, project_root=tmp_path, orchestrator=MagicMock()
        )
        assert isinstance(pod, PythonLanguagePod)

    def test_create_go_returns_go_pod(self, tmp_path):
        from src.agents.go_language_pod import GoLanguagePod
        llm_client = MagicMock()
        llm_client.generate.return_value = {
            "content": "", "tokens_used": 0, "latency_ms": 0, "model": "gpt-4o"
        }
        pod = PodFactory.create(
            "go", llm_client=llm_client, project_root=tmp_path, orchestrator=MagicMock()
        )
        assert isinstance(pod, GoLanguagePod)

    def test_unsupported_language_raises_value_error(self):
        with pytest.raises(ValueError, match="ruby"):
            PodFactory.create("ruby", llm_client=MagicMock())


# ---------------------------------------------------------------------------
# Integration: real pod stubs with known token counts
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_dual_language_run_populates_efficiency_report(self, tmp_path):
        py_pod = _stub_pod(tokens_per_phase=300)
        go_pod = _stub_pod(tokens_per_phase=150)
        runner = PolyglotTDDRunner(_factory({"python": py_pod, "go": go_pod}))

        result = runner.run(
            feature_requirement="User authentication with JWT",
            test_file=tmp_path / "auth_test.py",
            implementation_file=tmp_path / "auth.py",
            languages=["python", "go"],
        )

        assert isinstance(result.efficiency_report, EfficiencyReport)
        scores = {s.language: s for s in result.efficiency_report.scores}
        assert scores["python"].total_input_tokens == 300
        assert scores["go"].total_input_tokens == 150
        assert result.efficiency_report.comparison.most_efficient == "go"

        report_dict = result.efficiency_report.to_dict()
        assert "token_efficiency" in report_dict
        assert report_dict["token_efficiency"]["comparison"]["most_efficient"] == "go"
