"""Tests for IterativeTDDRunner's redundancy pre-check wiring.

Ported from AutonomousTDDAgent's redundancy_checker integration
(tests/test_tdd_agent_redundancy.py) -- the check now lives at the
IterativeTDDRunner level (where TestIncrement.test_name/description are
available) via an optional redundancy_checker constructor arg.
"""
from pathlib import Path

from src.agents.iterative_tdd_runner import IterativeTDDRunner
from src.agents.language_pod import PhaseResult, PodSpec, TokenUsage
from src.agents.redundancy_checker import RedundancyPreChecker


class _StubPod:
    def __init__(self):
        self.red_calls = []
        self.green_calls = []
        self.refactor_calls = []

    def run_red(self, spec: PodSpec) -> PhaseResult:
        self.red_calls.append(spec)
        return PhaseResult(passed=False, output="fails as expected")

    def run_green(self, spec: PodSpec) -> PhaseResult:
        self.green_calls.append(spec)
        return PhaseResult(passed=True, output="1 passed")

    def run_refactor(self, spec: PodSpec) -> PhaseResult:
        self.refactor_calls.append(spec)
        return PhaseResult(passed=True, output="1 passed")

    def token_usage(self) -> list[TokenUsage]:
        return []


class _StubIncrement:
    def __init__(self, test_name, description, test_file, impl_file):
        self.test_name = test_name
        self.description = description
        self.test_file = test_file
        self.implementation_file = impl_file
        self.dependencies = []
        self.scenario_context = None


class _StubPlanner:
    """Feeds a fixed sequence of increments, then COMPLETE."""

    def __init__(self, increments):
        from src.agents.incremental_planner import COMPLETE
        self._increments = list(increments)
        self._complete = COMPLETE
        self.recorded = []

    def next_increment(self, requirement, cycle_number, gherkin_context=None, gherkin_scenarios=None):
        if self._increments:
            return self._increments.pop(0)
        return self._complete

    def record_test_written(self, **kwargs):
        self.recorded.append(kwargs)


def _write_existing_test(test_file: Path, name: str):
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(f"def {name}():\n    assert add(1, 2) == 3\n")


class TestRedundancyPreCheck:
    def test_no_redundancy_checker_runs_every_increment(self, tmp_path):
        test_file = tmp_path / "test_add.py"
        pod = _StubPod()
        planner = _StubPlanner([
            _StubIncrement("test_add_returns_sum", "adds two numbers", test_file, tmp_path / "add.py"),
        ])
        runner = IterativeTDDRunner(pod, planner)  # redundancy_checker=None
        result = runner.run(requirement="calculator")

        assert len(pod.red_calls) == 1
        assert len(result.cycles) == 1

    def test_redundant_increment_is_skipped_without_running_pod(self, tmp_path):
        test_file = tmp_path / "test_add.py"
        _write_existing_test(test_file, "test_add_returns_sum")

        pod = _StubPod()
        planner = _StubPlanner([
            # Exact name match against the existing test -> redundant
            _StubIncrement("test_add_returns_sum", "adds two numbers", test_file, tmp_path / "add.py"),
        ])
        runner = IterativeTDDRunner(pod, planner, redundancy_checker=RedundancyPreChecker())
        result = runner.run(requirement="calculator")

        assert len(pod.red_calls) == 0   # never pulsed into the sandbox
        assert len(pod.green_calls) == 0
        assert len(result.cycles) == 1
        assert result.cycles[0].success is True   # skip counts as a completed cycle

    def test_non_redundant_increment_still_runs(self, tmp_path):
        test_file = tmp_path / "test_add.py"
        _write_existing_test(test_file, "test_add_returns_sum")

        pod = _StubPod()
        planner = _StubPlanner([
            _StubIncrement("test_add_negative_numbers", "handles negative edge case", test_file, tmp_path / "add.py"),
        ])
        runner = IterativeTDDRunner(pod, planner, redundancy_checker=RedundancyPreChecker())
        result = runner.run(requirement="calculator")

        assert len(pod.red_calls) == 1
        assert result.cycles[0].success is True

    def test_redundancy_check_runs_before_test_is_written_to_the_file(self, tmp_path):
        # No file on disk yet at all -> nothing to be redundant against.
        test_file = tmp_path / "test_add.py"
        pod = _StubPod()
        planner = _StubPlanner([
            _StubIncrement("test_add_returns_sum", "adds two numbers", test_file, tmp_path / "add.py"),
        ])
        runner = IterativeTDDRunner(pod, planner, redundancy_checker=RedundancyPreChecker())
        result = runner.run(requirement="calculator")

        assert len(pod.red_calls) == 1
        assert result.cycles[0].success is True

    def test_gherkin_driven_mode_also_pre_checks(self, tmp_path):
        test_file = tmp_path / "test_login.py"
        _write_existing_test(test_file, "test_login_ok")
        pod = _StubPod()

        class _ScenarioStubPlanner:
            def __init__(self):
                self._test_dir = tmp_path
                self._src_dir = tmp_path

            def next_increment_for_scenario(self, **kwargs):
                return _StubIncrement("test_login_ok", "login works", test_file, tmp_path / "login.py")

            def record_test_written(self, **kwargs):
                pass

        runner = IterativeTDDRunner(pod, _ScenarioStubPlanner(), redundancy_checker=RedundancyPreChecker())
        result = runner.run(
            requirement="user login",
            gherkin_context="Feature: login",
            gherkin_scenarios=[{"name": "ok"}],
            test_file=test_file,
            impl_file=tmp_path / "login.py",
        )

        assert len(pod.red_calls) == 0
        assert result.cycles[0].success is True
