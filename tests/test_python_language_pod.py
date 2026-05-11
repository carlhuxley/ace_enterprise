"""Tests for PythonLanguagePod (ace_enterprise-h3r)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agents.language_pod import LanguagePod, PhaseResult, PodSpec, TokenUsage
from src.agents.python_language_pod import PythonLanguagePod


def make_pod(tmp_path):
    """Build a PythonLanguagePod with a fully mocked agent."""
    from src.agents.autonomous_tdd_agent import TestResult

    agent = MagicMock()
    agent.project_root = tmp_path
    agent.test_dir = tmp_path / "tests"
    agent.src_dir = tmp_path / "src"
    agent.llm_client = MagicMock()
    agent.llm_client.generate.return_value = {
        "content": "def test_foo(): pass",
        "tokens_used": 120,
        "latency_ms": 50,
        "model": "gpt-4o",
    }
    agent._write_test.return_value = "def test_foo(): pass"
    agent._write_minimal_code.return_value = ("def foo(): pass", [])
    agent._refactor_code.return_value = "def foo(): pass  # refactored"
    agent._run_tests.return_value = TestResult(
        passed=True, failed=False, output="1 passed", test_count=1
    )
    return PythonLanguagePod(agent)


def failing_run_tests():
    from src.agents.autonomous_tdd_agent import TestResult
    return TestResult(passed=False, failed=True, output="FAILED", error="AssertionError")


def passing_run_tests():
    from src.agents.autonomous_tdd_agent import TestResult
    return TestResult(passed=True, failed=False, output="1 passed", test_count=1)


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

    def test_calls_write_test(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_red(spec(tmp_path))
        pod._agent._write_test.assert_called_once()

    def test_calls_run_tests(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_red(spec(tmp_path))
        pod._agent._run_tests.assert_called()

    def test_passed_reflects_test_failure(self, tmp_path):
        pod = make_pod(tmp_path)
        pod._agent._run_tests.return_value = failing_run_tests()
        result = pod.run_red(spec(tmp_path))
        assert not result.passed

    def test_passed_when_tests_unexpectedly_pass(self, tmp_path):
        pod = make_pod(tmp_path)
        pod._agent._run_tests.return_value = passing_run_tests()
        result = pod.run_red(spec(tmp_path))
        assert result.passed

    def test_write_test_exception_returns_failed_result(self, tmp_path):
        pod = make_pod(tmp_path)
        pod._agent._write_test.side_effect = RuntimeError("LLM failed")
        result = pod.run_red(spec(tmp_path))
        assert not result.passed
        assert result.error is not None


# ---------------------------------------------------------------------------
# run_green
# ---------------------------------------------------------------------------

class TestRunGreen:
    def test_returns_phase_result(self, tmp_path):
        pod = make_pod(tmp_path)
        pod._agent._run_tests.return_value = passing_run_tests()
        result = pod.run_green(spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_calls_write_minimal_code(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_green(spec(tmp_path))
        pod._agent._write_minimal_code.assert_called_once()

    def test_passed_reflects_test_result(self, tmp_path):
        pod = make_pod(tmp_path)
        pod._agent._run_tests.side_effect = [failing_run_tests(), passing_run_tests()]
        result = pod.run_green(spec(tmp_path))
        assert result.passed

    def test_failed_when_tests_still_fail(self, tmp_path):
        pod = make_pod(tmp_path)
        pod._agent._run_tests.return_value = failing_run_tests()
        result = pod.run_green(spec(tmp_path))
        assert not result.passed


# ---------------------------------------------------------------------------
# run_refactor
# ---------------------------------------------------------------------------

class TestRunRefactor:
    def test_returns_phase_result(self, tmp_path):
        pod = make_pod(tmp_path)
        result = pod.run_refactor(spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_calls_refactor_code(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_refactor(spec(tmp_path))
        pod._agent._refactor_code.assert_called_once()

    def test_passed_reflects_test_result(self, tmp_path):
        pod = make_pod(tmp_path)
        pod._agent._run_tests.return_value = passing_run_tests()
        result = pod.run_refactor(spec(tmp_path))
        assert result.passed


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
        # Simulate the agent calling generate during a phase by triggering
        # the intercepted generate directly (make_pod sets tokens_used=120).
        pod = make_pod(tmp_path)
        pod._agent.llm_client.generate("prompt")  # intercepted — adds 120 tokens
        pod._record_usage(1)
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
# Integration: protocol interface only (no direct agent calls)
# ---------------------------------------------------------------------------

class TestProtocolIntegration:
    def test_full_cycle_via_protocol_interface(self, tmp_path):
        pod = make_pod(tmp_path)
        pod._agent._run_tests.side_effect = [
            failing_run_tests(),   # RED: test fails (correct)
            failing_run_tests(),   # GREEN: run tests to get error
            passing_run_tests(),   # GREEN: tests pass after impl
            passing_run_tests(),   # REFACTOR: tests stay green
        ]

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
