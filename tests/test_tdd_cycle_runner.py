"""Tests for TDDCycleRunner (ace_enterprise-2qm).

Uses controlled pod doubles so we can drive exact pass/fail sequences
without touching the container or LLM.
"""
import dataclasses
from pathlib import Path

import pytest

from src.agents.language_pod import PhaseResult, PodSpec, TokenUsage
from src.agents.tdd_cycle_runner import CycleResult, TDDCycleRunner


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class ControlledPod:
    """Pod double: RED always fails; GREEN passes on Nth attempt; REFACTOR passes."""

    def __init__(self, green_pass_on: int = 1, refactor_passes: bool = True):
        self._green_pass_on = green_pass_on
        self._green_count = 0
        self._refactor_passes = refactor_passes
        self.green_specs: list[PodSpec] = []

    def run_red(self, spec: PodSpec) -> PhaseResult:
        return PhaseResult(passed=False, output="test fails: no impl", error=None)

    def run_green(self, spec: PodSpec) -> PhaseResult:
        self.green_specs.append(spec)
        self._green_count += 1
        if self._green_count >= self._green_pass_on:
            return PhaseResult(passed=True, output="1 passed", error=None)
        return PhaseResult(passed=False, output="AssertionError: expected 3 got 0", error=None)

    def run_refactor(self, spec: PodSpec) -> PhaseResult:
        if self._refactor_passes:
            return PhaseResult(passed=True, output="1 passed", error=None)
        return PhaseResult(passed=False, output="FAILED", error="refactor broke tests")

    def token_usage(self) -> list[TokenUsage]:
        return []


class AbortingRedPod(ControlledPod):
    """RED returns a forbidden import error → should abort cycle."""

    def run_red(self, spec: PodSpec) -> PhaseResult:
        return PhaseResult(passed=False, output="", error="ForbiddenImport: os")


class AbortingGreenPod(ControlledPod):
    """GREEN returns a security breach → should abort without further retries."""

    def run_green(self, spec: PodSpec) -> PhaseResult:
        self.green_specs.append(spec)
        return PhaseResult(passed=False, output="", error="SecurityBreach: hash mismatch")


class TokenPod(ControlledPod):
    """Accumulates one TokenUsage record per phase call."""

    def __init__(self):
        super().__init__()
        self._usage: list[TokenUsage] = []

    def run_red(self, spec: PodSpec) -> PhaseResult:
        self._usage.append(TokenUsage(cycle_number=spec.cycle_number, input_tokens=50, output_tokens=0))
        return super().run_red(spec)

    def run_green(self, spec: PodSpec) -> PhaseResult:
        self._usage.append(TokenUsage(cycle_number=spec.cycle_number, input_tokens=150, output_tokens=0))
        return super().run_green(spec)

    def run_refactor(self, spec: PodSpec) -> PhaseResult:
        self._usage.append(TokenUsage(cycle_number=spec.cycle_number, input_tokens=80, output_tokens=0))
        return super().run_refactor(spec)

    def token_usage(self) -> list[TokenUsage]:
        return list(self._usage)


def _spec(tmp_path: Path) -> PodSpec:
    return PodSpec(
        feature_requirement="add two numbers",
        test_file=tmp_path / "test_add.py",
        implementation_file=tmp_path / "add.py",
        cycle_number=1,
    )


# ---------------------------------------------------------------------------
# Behavior 1: full happy-path RED → GREEN → REFACTOR (tracer bullet)
# ---------------------------------------------------------------------------

def test_full_cycle_success(tmp_path):
    runner = TDDCycleRunner(ControlledPod())
    result = runner.run(_spec(tmp_path))

    assert isinstance(result, CycleResult)
    assert result.success is True
    assert result.red_result.passed is False
    assert result.green_result.passed is True
    assert result.refactor_result is not None
    assert result.refactor_result.passed is True


# ---------------------------------------------------------------------------
# Behavior 2: RED abort (ForbiddenImport) → no GREEN attempted
# ---------------------------------------------------------------------------

def test_red_abort_skips_green_and_refactor(tmp_path):
    pod = AbortingRedPod()
    runner = TDDCycleRunner(pod)
    result = runner.run(_spec(tmp_path))

    assert result.success is False
    assert result.green_attempts == 0
    assert result.refactor_result is None
    assert "RED aborted" in (result.error or "")


# ---------------------------------------------------------------------------
# Behavior 3: GREEN fails first attempt, succeeds on second
# ---------------------------------------------------------------------------

def test_green_retry_succeeds_on_second_attempt(tmp_path):
    runner = TDDCycleRunner(ControlledPod(green_pass_on=2))
    result = runner.run(_spec(tmp_path))

    assert result.success is True
    assert result.green_attempts == 2


# ---------------------------------------------------------------------------
# Behavior 4: GREEN exhausts all retries → success=False
# ---------------------------------------------------------------------------

def test_green_exhausts_retries_returns_failure(tmp_path):
    runner = TDDCycleRunner(ControlledPod(green_pass_on=999), max_green_attempts=3)
    result = runner.run(_spec(tmp_path))

    assert result.success is False
    assert result.green_attempts == 3
    assert result.refactor_result is None


# ---------------------------------------------------------------------------
# Behavior 5: REFACTOR fails → success=False with refactor_result populated
# ---------------------------------------------------------------------------

def test_refactor_failure_returns_success_false(tmp_path):
    runner = TDDCycleRunner(ControlledPod(refactor_passes=False))
    result = runner.run(_spec(tmp_path))

    assert result.success is False
    assert result.refactor_result is not None
    assert result.refactor_result.passed is False


# ---------------------------------------------------------------------------
# Behavior 6: GREEN abort (SecurityBreach) stops retries immediately
# ---------------------------------------------------------------------------

def test_green_abort_stops_retries(tmp_path):
    pod = AbortingGreenPod()
    runner = TDDCycleRunner(pod, max_green_attempts=3)
    result = runner.run(_spec(tmp_path))

    assert result.success is False
    assert len(pod.green_specs) == 1  # only one attempt made


# ---------------------------------------------------------------------------
# Behavior 7: error_output from failed GREEN is passed to next attempt
# ---------------------------------------------------------------------------

def test_error_output_threaded_to_retry(tmp_path):
    pod = ControlledPod(green_pass_on=2)
    runner = TDDCycleRunner(pod)
    runner.run(_spec(tmp_path))

    # First attempt gets blank error_output
    assert pod.green_specs[0].error_output == ""
    # Second attempt gets the output from the first failure
    assert "AssertionError" in pod.green_specs[1].error_output


# ---------------------------------------------------------------------------
# Behavior 8: token_usage from pod is captured in CycleResult
# ---------------------------------------------------------------------------

def test_token_usage_carried_in_result(tmp_path):
    runner = TDDCycleRunner(TokenPod())
    result = runner.run(_spec(tmp_path))

    # full cycle: red + green + refactor → 3 records
    assert len(result.token_usage) == 3
    assert result.token_usage[0].input_tokens == 50   # red
    assert result.token_usage[1].input_tokens == 150  # green
    assert result.token_usage[2].input_tokens == 80   # refactor


# ---------------------------------------------------------------------------
# Behavior 9: ExperimentLogger.log_tdd_cycle called after each cycle
# ---------------------------------------------------------------------------

def test_experiment_logger_called_on_success(tmp_path):
    calls = []

    class _Logger:
        def log_tdd_cycle(self, **kwargs):
            calls.append(kwargs)

    spec = _spec(tmp_path)
    spec.test_file.write_text("# test")
    spec.implementation_file.write_text("# impl")

    runner = TDDCycleRunner(ControlledPod(), experiment_logger=_Logger(), playbook_id="test-pb")
    runner.run(spec)

    assert len(calls) == 1
    c = calls[0]
    assert c["cycle_number"] == 1
    assert c["requirement"] == "add two numbers"
    assert c["green_passed"] is True
    assert c["red_passed"] is False
    assert c["playbook_id"] == "test-pb"
    assert c["retry_count"] == 1


def test_experiment_logger_called_on_red_abort(tmp_path):
    calls = []

    class _Logger:
        def log_tdd_cycle(self, **kwargs):
            calls.append(kwargs)

    runner = TDDCycleRunner(AbortingRedPod(), experiment_logger=_Logger())
    runner.run(_spec(tmp_path))

    assert len(calls) == 1
    assert calls[0]["green_passed"] is False


def test_no_experiment_logger_does_not_raise(tmp_path):
    runner = TDDCycleRunner(ControlledPod())   # no logger
    result = runner.run(_spec(tmp_path))
    assert result.success is True


# ---------------------------------------------------------------------------
# Behavior 10: Reflector + Curator learning loop
# ---------------------------------------------------------------------------

class _FakeDeltaBullet:
    def __init__(self, content, section="strategies_and_hard_rules"):
        self.content = content
        self.section = section


class _FakeReflectorOutput:
    pass


class _FakeCuratorOutput:
    def __init__(self, bullets):
        self.delta_bullets = bullets
        self.reasoning = "test reasoning"


class _SpyReflector:
    def __init__(self):
        self.calls = []

    def reflect(self, task, generator_output, environment_feedback):
        self.calls.append((task, generator_output, environment_feedback))
        return _FakeReflectorOutput()


class _SpyCurator:
    def __init__(self, bullets=None):
        self.curate_calls = []
        self.apply_calls = []
        self._bullets = bullets or [_FakeDeltaBullet("always use pathlib")]

    def curate(self, reflector_output, playbook_id, task_context=None):
        self.curate_calls.append((reflector_output, playbook_id))
        return _FakeCuratorOutput(self._bullets)

    def apply_updates(self, playbook_id, curator_output):
        self.apply_calls.append((playbook_id, curator_output))


def test_reflector_and_curator_called_on_success(tmp_path):
    reflector = _SpyReflector()
    curator = _SpyCurator()
    runner = TDDCycleRunner(
        ControlledPod(),
        reflector=reflector,
        curator=curator,
        playbook_id="test-pb",
    )
    result = runner.run(_spec(tmp_path))

    assert result.success is True
    assert len(reflector.calls) == 1
    assert len(curator.curate_calls) == 1
    assert curator.curate_calls[0][1] == "test-pb"
    assert len(curator.apply_calls) == 1


def test_learned_bullets_in_cycle_result(tmp_path):
    curator = _SpyCurator(bullets=[
        _FakeDeltaBullet("use dataclasses for value objects"),
        _FakeDeltaBullet("avoid mutable defaults"),
    ])
    runner = TDDCycleRunner(ControlledPod(), reflector=_SpyReflector(), curator=curator)
    result = runner.run(_spec(tmp_path))

    assert len(result.learned_bullets) == 2
    assert result.learned_bullets[0].content == "use dataclasses for value objects"


def test_learning_skipped_on_green_failure(tmp_path):
    reflector = _SpyReflector()
    curator = _SpyCurator()
    runner = TDDCycleRunner(
        ControlledPod(green_pass_on=999),
        max_green_attempts=1,
        reflector=reflector,
        curator=curator,
    )
    result = runner.run(_spec(tmp_path))

    assert result.success is False
    assert len(reflector.calls) == 0
    assert len(curator.curate_calls) == 0
    assert result.learned_bullets == []


def test_learning_skipped_on_red_abort(tmp_path):
    reflector = _SpyReflector()
    runner = TDDCycleRunner(AbortingRedPod(), reflector=reflector, curator=_SpyCurator())
    runner.run(_spec(tmp_path))
    assert len(reflector.calls) == 0


def test_learning_failure_does_not_crash_cycle(tmp_path):
    class _BrokenCurator(_SpyCurator):
        def curate(self, *args, **kwargs):
            raise RuntimeError("DB connection lost")

    runner = TDDCycleRunner(
        ControlledPod(),
        reflector=_SpyReflector(),
        curator=_BrokenCurator(),
    )
    result = runner.run(_spec(tmp_path))

    assert result.success is True          # cycle still succeeds
    assert result.learned_bullets == []    # bullets empty on error


def test_no_reflector_leaves_learned_bullets_empty(tmp_path):
    runner = TDDCycleRunner(ControlledPod())   # neither reflector nor curator
    result = runner.run(_spec(tmp_path))
    assert result.learned_bullets == []
