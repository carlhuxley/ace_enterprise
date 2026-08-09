"""Tests for PythonLanguagePod (ace_enterprise-h3r).

Rewritten for the worker + orchestrator architecture (ace_enterprise-vzp) —
the original PythonLanguagePod(agent) constructor and internal
_write_test/_write_minimal_code/_refactor_code/_run_tests delegation were
removed in 76980c8 in favour of WorkerAgent + PodmanOrchestrator.
"""
from unittest.mock import MagicMock

import pytest

from src.agents.language_pod import LanguagePod, PhaseResult, PodSpec, TokenUsage
from src.agents.python_language_pod import PythonLanguagePod


def make_pod(tmp_path, pulse_result=None):
    """Build a PythonLanguagePod with a fully mocked worker + orchestrator.

    generate_test/generate_implementation call llm_client.generate via
    side_effect (not just return_value) so the pod's token interception —
    which wraps worker.llm_client.generate, not the worker's own methods —
    actually has something to intercept, matching how the real WorkerAgent
    calls self.llm_client.generate() internally.
    """
    worker = MagicMock()
    worker.llm_client = MagicMock()
    worker.llm_client.generate.return_value = {
        "content": "def test_foo(): pass",
        "prompt_tokens": 120,
        "completion_tokens": 0,
        "tokens_used": 120,
        "latency_ms": 50,
        "model": "gpt-4o",
    }

    def _generate_test(*args, **kwargs):
        worker.llm_client.generate("test prompt")
        return "def test_foo(): pass"

    def _generate_implementation(*args, **kwargs):
        worker.llm_client.generate("impl prompt")
        return "def foo(): pass"

    worker.generate_test.side_effect = _generate_test
    worker.generate_implementation.side_effect = _generate_implementation
    worker.generate_refactor.return_value = "def foo(): pass  # refactored"

    orchestrator = MagicMock()
    orchestrator.pulse.return_value = pulse_result or PhaseResult(
        passed=True, output="1 passed", error=None
    )
    return PythonLanguagePod(worker, tmp_path, orchestrator)


def spec(tmp_path, cycle=1):
    return PodSpec(
        feature_requirement="Process an order and return confirmation",
        test_file=tmp_path / "tests" / "test_order.py",
        implementation_file=tmp_path / "src" / "order.py",
        cycle_number=cycle,
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestProtocolConformance:
    def test_isinstance_language_pod(self, tmp_path):
        pod = make_pod(tmp_path)
        assert isinstance(pod, LanguagePod)

    def test_has_all_required_methods(self, tmp_path):
        pod = make_pod(tmp_path)
        assert callable(pod.run_red)
        assert callable(pod.run_green)
        assert callable(pod.run_refactor)
        assert callable(pod.token_usage)


# ---------------------------------------------------------------------------
# run_red
# ---------------------------------------------------------------------------

class TestRunRed:
    def test_returns_phase_result(self, tmp_path):
        pod = make_pod(tmp_path)
        result = pod.run_red(spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_calls_generate_test(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_red(spec(tmp_path))
        pod._worker.generate_test.assert_called_once()

    def test_calls_orchestrator_pulse(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_red(spec(tmp_path))
        pod._orchestrator.pulse.assert_called_once()

    def test_passed_reflects_pulse_result(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=False, output="FAILED", error=None))
        result = pod.run_red(spec(tmp_path))
        assert not result.passed

    def test_passed_when_pulse_passes(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=True, output="1 passed", error=None))
        result = pod.run_red(spec(tmp_path))
        assert result.passed

    def test_generate_test_exception_returns_failed_result(self, tmp_path):
        pod = make_pod(tmp_path)
        pod._worker.generate_test.side_effect = RuntimeError("LLM failed")
        result = pod.run_red(spec(tmp_path))
        assert not result.passed
        assert result.error is not None

    def test_commits_test_file_to_disk(self, tmp_path):
        pod = make_pod(tmp_path)
        s = spec(tmp_path)
        pod.run_red(s)
        assert s.test_file.exists()

    def test_forbidden_import_blocks_before_container(self, tmp_path):
        pod = make_pod(tmp_path)
        pod._worker.generate_test.side_effect = lambda *a, **kw: "import os\ndef test_foo(): os.system('x')"
        result = pod.run_red(spec(tmp_path))
        assert result.error is not None and result.error.startswith("ForbiddenImport:")
        pod._orchestrator.pulse.assert_not_called()


# ---------------------------------------------------------------------------
# run_green
# ---------------------------------------------------------------------------

class TestRunGreen:
    def test_returns_phase_result(self, tmp_path):
        pod = make_pod(tmp_path)
        result = pod.run_green(spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_calls_generate_implementation(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_green(spec(tmp_path))
        pod._worker.generate_implementation.assert_called_once()

    def test_passed_reflects_pulse_result(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=True, output="1 passed", error=None))
        result = pod.run_green(spec(tmp_path))
        assert result.passed

    def test_failed_when_pulse_fails(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=False, output="FAILED", error=None))
        result = pod.run_green(spec(tmp_path))
        assert not result.passed

    def test_does_not_commit_impl_file_when_pulse_fails(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=False, output="FAILED", error=None))
        s = spec(tmp_path)
        pod.run_green(s)
        assert not s.implementation_file.exists()

    def test_commits_impl_file_when_pulse_passes(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=True, output="1 passed", error=None))
        s = spec(tmp_path)
        pod.run_green(s)
        assert s.implementation_file.exists()

    def test_forbidden_import_blocks_before_container(self, tmp_path):
        pod = make_pod(tmp_path)
        pod._worker.generate_implementation.side_effect = (
            lambda *a, **kw: "import subprocess\ndef foo(): subprocess.run(['x'])"
        )
        result = pod.run_green(spec(tmp_path))
        assert result.error is not None and result.error.startswith("ForbiddenImport:")
        pod._orchestrator.pulse.assert_not_called()


# ---------------------------------------------------------------------------
# run_refactor
#
# Calls worker.generate_refactor(spec, current_code=...) to produce a
# refactored implementation, then pulses test+refactored-impl through the
# orchestrator. Only commits the refactor to disk if the pulse still passes —
# a failed refactor must not clobber a working implementation on disk
# (ace_enterprise-3dg; previously this was a no-op verification step that
# never called generate_refactor at all).
# ---------------------------------------------------------------------------

class TestRunRefactor:
    def test_returns_phase_result(self, tmp_path):
        pod = make_pod(tmp_path)
        result = pod.run_refactor(spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_calls_generate_refactor(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_refactor(spec(tmp_path))
        pod._worker.generate_refactor.assert_called_once()

    def test_passes_current_code_to_generate_refactor(self, tmp_path):
        pod = make_pod(tmp_path)
        s = spec(tmp_path)
        s.implementation_file.parent.mkdir(parents=True, exist_ok=True)
        s.implementation_file.write_text("def foo(): pass  # original")

        pod.run_refactor(s)

        _, kwargs = pod._worker.generate_refactor.call_args
        assert kwargs["current_code"] == "def foo(): pass  # original"

    def test_pulses_test_and_refactored_impl(self, tmp_path):
        pod = make_pod(tmp_path)
        pod._worker.generate_refactor.return_value = "def foo(): pass  # refactored"
        s = spec(tmp_path)
        s.test_file.parent.mkdir(parents=True, exist_ok=True)
        s.test_file.write_text("def test_foo(): pass")

        pod.run_refactor(s)

        files = pod._orchestrator.pulse.call_args.args[0]
        assert files[s.test_file.name] == "def test_foo(): pass"
        assert files[s.implementation_file.name] == "def foo(): pass  # refactored"

    def test_passed_reflects_pulse_result(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=True, output="1 passed", error=None))
        result = pod.run_refactor(spec(tmp_path))
        assert result.passed

    def test_commits_refactored_code_when_pulse_passes(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=True, output="1 passed", error=None))
        pod._worker.generate_refactor.return_value = "def foo(): pass  # refactored"
        s = spec(tmp_path)

        pod.run_refactor(s)

        assert s.implementation_file.read_text() == "def foo(): pass  # refactored"

    def test_does_not_clobber_working_impl_when_refactor_fails(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=False, output="FAILED", error=None))
        pod._worker.generate_refactor.return_value = "def foo(): broken_refactor"
        s = spec(tmp_path)
        s.implementation_file.parent.mkdir(parents=True, exist_ok=True)
        s.implementation_file.write_text("def foo(): pass  # working original")

        result = pod.run_refactor(s)

        assert not result.passed
        assert s.implementation_file.read_text() == "def foo(): pass  # working original"

    def test_forbidden_import_blocks_before_container(self, tmp_path):
        pod = make_pod(tmp_path)
        pod._worker.generate_refactor.return_value = "import os\ndef foo(): os.system('x')"
        result = pod.run_refactor(spec(tmp_path))
        assert result.error is not None and result.error.startswith("ForbiddenImport:")
        pod._orchestrator.pulse.assert_not_called()


# ---------------------------------------------------------------------------
# token_usage
# ---------------------------------------------------------------------------

class TestTokenUsage:
    def test_returns_list(self, tmp_path):
        pod = make_pod(tmp_path)
        assert isinstance(pod.token_usage(), list)

    def test_empty_before_any_phase(self, tmp_path):
        pod = make_pod(tmp_path)
        assert pod.token_usage() == []

    def test_records_token_usage_after_red(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_red(spec(tmp_path, cycle=1))
        usage = pod.token_usage()
        assert len(usage) == 1
        assert usage[0].cycle_number == 1
        assert usage[0].input_tokens == 120

    def test_accumulates_across_cycles(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_red(spec(tmp_path, cycle=1))
        pod.run_red(spec(tmp_path, cycle=2))
        assert len(pod.token_usage()) == 2
        assert pod.token_usage()[0].cycle_number == 1
        assert pod.token_usage()[1].cycle_number == 2

    def test_token_usage_entries_are_token_usage_type(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_red(spec(tmp_path, cycle=1))
        assert all(isinstance(u, TokenUsage) for u in pod.token_usage())


# ---------------------------------------------------------------------------
# Integration: full RED -> GREEN -> REFACTOR via the protocol interface
# ---------------------------------------------------------------------------

class TestProtocolIntegration:
    def test_full_cycle_via_protocol_interface(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=True, output="1 passed", error=None))
        s = spec(tmp_path, cycle=1)

        red = pod.run_red(s)
        assert isinstance(red, PhaseResult)

        green = pod.run_green(s)
        assert isinstance(green, PhaseResult)

        refactor = pod.run_refactor(s)
        assert isinstance(refactor, PhaseResult)

        usage = pod.token_usage()
        assert len(usage) == 3
        assert all(isinstance(u, TokenUsage) for u in usage)
