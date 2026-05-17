"""
Hazardous Pipeline — Milestone 3: ReDoS Attack.

Scenario: an email/input validator feature. A naive LLM implementation uses
a catastrophically backtracking regex such as ^(a+)+$. Without protection,
matching against a crafted input spins forever and pegs a CPU core.

Verifies that the safety sandwich defuses the attack at every relevant layer:

  Unit layer
    - A known ReDoS pattern triggers a timeout when run directly with
      signal-based timeout (proves the pattern is genuinely dangerous)

  Container layer (real Podman)
    - The container's pytest-timeout (10 s) kills the hung test and reports
      FAILED rather than hanging indefinitely; PodmanRunner.send_pulse()
      returns a PhaseResult with passed=False within a bounded wall-clock time

    - A safe re.fullmatch alternative (no catastrophic backtracking) passes
      all tests within the timeout

  TDDCycleRunner layer
    - A pod whose GREEN returns the timeout-failure output is treated as a
      retriable failure (not an abort), so the runner does retry
"""
import re
import shutil
import signal
import time

import pytest

from src.agents.language_pod import PhaseResult, PodSpec
from src.agents.podman_orchestrator import PodmanOrchestrator
from src.agents.tdd_cycle_runner import TDDCycleRunner, _is_abort

# ---------------------------------------------------------------------------
# Representative LLM outputs
# ---------------------------------------------------------------------------

# Catastrophically backtracking regex — matches valid input but explodes on
# crafted adversarial strings like "aaaaaaaaaaaaaaaaaaaaaaaaaab"
REDOS_IMPL = """\
import re


def validate_input(s: str) -> bool:
    # BUG: catastrophic backtracking on adversarial input
    return bool(re.match(r"^(a+)+$", s))
"""

# Safe alternative: anchored character-class, no nested quantifiers
SAFE_IMPL = """\
import re


def validate_input(s: str) -> bool:
    return bool(re.fullmatch(r"a+", s))
"""

# Test suite the LLM would also generate
TEST_FILE = """\
from validator import validate_input


def test_valid_input_passes():
    assert validate_input("aaa") is True


def test_invalid_input_fails():
    assert validate_input("b") is False


def test_adversarial_input_does_not_hang():
    # This string causes catastrophic backtracking in naive regexes.
    # pytest-timeout will kill the test after 10 s if it hangs.
    evil = "a" * 28 + "b"
    result = validate_input(evil)
    assert result is False
"""

# ---------------------------------------------------------------------------
# Unit: prove the pattern is genuinely dangerous (signal-based local timeout)
# ---------------------------------------------------------------------------

def _alarm_handler(signum, frame):
    raise TimeoutError("ReDoS confirmed: regex did not return in time")


def test_redos_pattern_is_genuinely_dangerous():
    """The catastrophic regex must not finish within 1 s on the adversarial input."""
    evil = "a" * 28 + "b"
    signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(1)
    try:
        re.match(r"^(a+)+$", evil)
        timed_out = False
    except TimeoutError:
        timed_out = True
    finally:
        signal.alarm(0)
    assert timed_out, "Expected catastrophic backtracking but regex returned quickly"


# ---------------------------------------------------------------------------
# Container layer (real Podman)
# ---------------------------------------------------------------------------

skip_no_podman = pytest.mark.skipif(
    not shutil.which("podman"),
    reason="podman not in PATH",
)


@skip_no_podman
def test_redos_impl_fails_within_bounded_time(shared_podman_runner, tmp_path):
    """
    The container's pytest-timeout must kill the hung test and return a
    failed PhaseResult. The call to orchestrator.pulse() must itself return
    within a reasonable wall-clock window (well under 60 s).
    """
    orchestrator = PodmanOrchestrator(
        runner=shared_podman_runner,
        work_dir=tmp_path / "work",
    )
    start = time.monotonic()
    result = orchestrator.pulse({
        "validator.py": REDOS_IMPL,
        "test_validator.py": TEST_FILE,
    })
    elapsed = time.monotonic() - start

    assert not result.passed, "ReDoS impl should fail due to timeout"
    assert elapsed < 60, f"pulse() took {elapsed:.1f}s — timeout did not fire"
    assert "FAILED" in (result.output or "") or result.exit_code != 0


@skip_no_podman
def test_safe_impl_passes_in_container(shared_podman_runner, tmp_path):
    orchestrator = PodmanOrchestrator(
        runner=shared_podman_runner,
        work_dir=tmp_path / "work",
    )
    result = orchestrator.pulse({
        "validator.py": SAFE_IMPL,
        "test_validator.py": TEST_FILE,
    })
    assert result.passed, f"Safe impl failed:\n{result.output}\n{result.error}"


# ---------------------------------------------------------------------------
# TDDCycleRunner layer: timeout failure is retriable, not an abort
# ---------------------------------------------------------------------------

class _ReDoSPod:
    """
    Simulates a pod where GREEN returns a pytest-timeout failure on the first
    attempt, then succeeds on the second (LLM fixed the regex).
    """

    def __init__(self):
        self._green_calls = 0

    def run_red(self, spec):
        return PhaseResult(passed=False, output="1 failed", error=None)

    def run_green(self, spec):
        self._green_calls += 1
        if self._green_calls == 1:
            return PhaseResult(
                passed=False,
                output="FAILED test_validator.py::test_adversarial_input_does_not_hang - Failed: Timeout >10.0s",
                error=None,
            )
        return PhaseResult(passed=True, output="3 passed", error=None)

    def run_refactor(self, spec):
        return PhaseResult(passed=True, output="3 passed", error=None)

    def token_usage(self):
        return []


def test_timeout_failure_is_not_an_abort():
    """A pytest-timeout failure has no special prefix — _is_abort() must return False."""
    timeout_result = PhaseResult(
        passed=False,
        output="FAILED — Timeout >10.0s",
        error=None,
    )
    assert _is_abort(timeout_result) is False


def test_cycle_runner_retries_after_timeout_failure():
    pod = _ReDoSPod()
    runner = TDDCycleRunner(pod, max_green_attempts=3)
    spec = PodSpec(
        feature_requirement="validate input strings",
        test_file=__import__("pathlib").Path("/tmp/test_validator.py"),
        implementation_file=__import__("pathlib").Path("/tmp/validator.py"),
        cycle_number=1,
    )
    result = runner.run(spec)

    assert result.success is True
    assert result.green_attempts == 2, "runner should retry after timeout and succeed on second attempt"
