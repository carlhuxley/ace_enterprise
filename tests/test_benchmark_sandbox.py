"""Regression test for benchmarks.sandbox.LocalSubprocessRunner's timeout path.

Found via forensic analysis of a real benchmark run: conc_producer_consumer
correctly deadlocked (the task's intended trap -- see benchmarks/tasks.py),
but the subsequent Reflector/Curator step crashed with "Object of type bytes
is not JSON serializable" instead of curating a bullet from it. Root cause:
subprocess.TimeoutExpired.stdout/.stderr are the raw bytes captured before
the timeout fired -- unlike subprocess.run()'s normal return path, they are
NOT decoded even though text=True was passed. Left as bytes, that silently
poisons PulseResult.stdout -> PhaseResult.output ->
EnvironmentFeedback.test_report, which Reflector json.dumps()s.
"""
import json

from benchmarks.sandbox import LocalSubprocessRunner
from src.agents.podman_orchestrator import PodmanOrchestrator
from src.storage.schemas import EnvironmentFeedback

_HANGING_TEST = """
import time

def test_hangs_forever():
    time.sleep(5)
"""


def test_timeout_output_is_str_not_bytes():
    runner = LocalSubprocessRunner(test_timeout=1)
    result = runner.send_pulse({"test_solution.py": _HANGING_TEST})

    assert result.exit_code != 0
    assert isinstance(result.stdout, str), f"expected str, got {type(result.stdout)}"
    assert isinstance(result.stderr, str), f"expected str, got {type(result.stderr)}"
    assert "timed out" in result.stderr.lower()


def test_timeout_result_survives_environment_feedback_json_serialization():
    """The actual failure mode: EnvironmentFeedback.test_report gets
    json.dumps()'d by Reflector._build_analysis_prompt -- this must not
    raise even when the phase timed out."""
    runner = LocalSubprocessRunner(test_timeout=1)
    orchestrator = PodmanOrchestrator(runner=runner, started=False)

    phase = orchestrator.pulse({"test_solution.py": _HANGING_TEST})

    env_feedback = EnvironmentFeedback(
        result="FAILED",
        feedback=(phase.error or phase.output or "")[:4000],
        test_report={"stdout": phase.output, "error": phase.error},
    )
    # Must not raise TypeError: Object of type bytes is not JSON serializable
    json.dumps(env_feedback.test_report)
