"""Tests for the LanguagePod protocol (ace_enterprise-g1p)."""
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.agents.language_pod import LanguagePod, PhaseResult, PodSpec, TokenUsage


# ---------------------------------------------------------------------------
# Structural / schema tests
# ---------------------------------------------------------------------------

class TestPodSpec:
    def test_required_fields(self, tmp_path):
        spec = PodSpec(
            feature_requirement="Process an order",
            test_file=tmp_path / "tests" / "test_order.py",
            implementation_file=tmp_path / "src" / "order.py",
            cycle_number=1,
        )
        assert spec.feature_requirement == "Process an order"
        assert spec.cycle_number == 1

    def test_paths_are_path_objects(self, tmp_path):
        spec = PodSpec(
            feature_requirement="foo",
            test_file=tmp_path / "test_foo.py",
            implementation_file=tmp_path / "foo.py",
            cycle_number=1,
        )
        assert isinstance(spec.test_file, Path)
        assert isinstance(spec.implementation_file, Path)


class TestPhaseResult:
    def test_passed_result(self):
        r = PhaseResult(passed=True, output="1 passed")
        assert r.passed
        assert r.error is None

    def test_failed_result_with_error(self):
        r = PhaseResult(passed=False, output="FAILED", error="AssertionError")
        assert not r.passed
        assert r.error == "AssertionError"

    def test_no_token_fields(self):
        r = PhaseResult(passed=True, output="ok")
        assert not hasattr(r, "input_tokens")
        assert not hasattr(r, "output_tokens")


class TestTokenUsage:
    def test_fields(self):
        t = TokenUsage(cycle_number=2, input_tokens=500, output_tokens=300)
        assert t.cycle_number == 2
        assert t.input_tokens == 500
        assert t.output_tokens == 300


# ---------------------------------------------------------------------------
# Protocol conformance tests
# ---------------------------------------------------------------------------

class TestLanguagePodProtocol:
    def test_runtime_checkable(self, tmp_path):
        """isinstance() works without importing the concrete type."""
        class MyPod:
            def run_red(self, spec): return PhaseResult(passed=False, output="red")
            def run_green(self, spec): return PhaseResult(passed=True, output="green")
            def run_refactor(self, spec): return PhaseResult(passed=True, output="refactored")
            def token_usage(self): return []

        pod = MyPod()
        assert isinstance(pod, LanguagePod)

    def test_missing_method_fails_isinstance(self):
        class IncompletePod:
            def run_red(self, spec): ...
            def run_green(self, spec): ...
            # run_refactor missing
            def token_usage(self): ...

        assert not isinstance(IncompletePod(), LanguagePod)

    def test_no_language_specific_names_in_interface(self):
        """Protocol source must not mention 'python' or 'go' (case-insensitive)."""
        import inspect
        import src.agents.language_pod as mod
        source = inspect.getsource(mod)
        # Strip comments and strings for a clean check
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            lower = stripped.lower()
            assert "python" not in lower, f"Language-specific name in interface: {line}"
            assert " go " not in lower and lower.startswith("go") is False or "gopher" in lower, \
                f"Possible language-specific name: {line}"

    def test_protocol_methods_return_correct_types(self, tmp_path):
        """A conforming pod returns the right types from all methods."""
        class GoodPod:
            def run_red(self, spec: PodSpec) -> PhaseResult:
                return PhaseResult(passed=False, output="failing test")

            def run_green(self, spec: PodSpec) -> PhaseResult:
                return PhaseResult(passed=True, output="passing")

            def run_refactor(self, spec: PodSpec) -> PhaseResult:
                return PhaseResult(passed=True, output="formatted")

            def token_usage(self) -> list[TokenUsage]:
                return [TokenUsage(cycle_number=1, input_tokens=100, output_tokens=50)]

        pod = GoodPod()
        spec = PodSpec(
            feature_requirement="test",
            test_file=tmp_path / "test_foo.py",
            implementation_file=tmp_path / "foo.py",
            cycle_number=1,
        )

        red = pod.run_red(spec)
        assert isinstance(red, PhaseResult)
        assert not red.passed

        green = pod.run_green(spec)
        assert isinstance(green, PhaseResult)
        assert green.passed

        refactor = pod.run_refactor(spec)
        assert isinstance(refactor, PhaseResult)

        usage = pod.token_usage()
        assert isinstance(usage, list)
        assert all(isinstance(u, TokenUsage) for u in usage)

    def test_token_usage_aggregates_across_cycles(self, tmp_path):
        class MultiCyclePod:
            def run_red(self, spec): return PhaseResult(passed=False, output="")
            def run_green(self, spec): return PhaseResult(passed=True, output="")
            def run_refactor(self, spec): return PhaseResult(passed=True, output="")
            def token_usage(self):
                return [
                    TokenUsage(cycle_number=1, input_tokens=200, output_tokens=100),
                    TokenUsage(cycle_number=2, input_tokens=180, output_tokens=90),
                ]

        pod = MultiCyclePod()
        usage = pod.token_usage()
        assert len(usage) == 2
        total_in = sum(u.input_tokens for u in usage)
        assert total_in == 380
