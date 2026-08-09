"""Tests for Bandit gate in PodmanOrchestrator (ace_enterprise-c5d)."""
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from src.agents.language_pod import PhaseResult
from src.agents.podman_orchestrator import ContainerRunner, PodmanOrchestrator, PulseResult


class BanditSubprocessRunner:
    """Test double: runs pytest then bandit on the host, mimicking the container entrypoint."""

    def __init__(self):
        self._alive = True

    def send_pulse(self, files: dict[str, str]) -> PulseResult:
        with tempfile.TemporaryDirectory() as ws:
            ws_path = Path(ws)
            for name, content in files.items():
                (ws_path / name).write_text(content)
            pytest_result = subprocess.run(
                [sys.executable, "-m", "pytest", ws, "-v", "--tb=short"],
                capture_output=True,
                text=True,
            )
            bandit_result = subprocess.run(
                [sys.executable, "-m", "bandit", "-r", ws, "--format", "json", "-q"],
                capture_output=True,
                text=True,
            )
        return _parse_bandit_pulse(pytest_result, bandit_result)

    def is_alive(self) -> bool:
        return self._alive

    def start(self) -> None:
        self._alive = True

    def stop(self) -> None:
        self._alive = False


def _parse_bandit_pulse(pytest_result, bandit_result) -> PulseResult:
    import json

    high = medium = low = 0
    bandit_output = bandit_result.stdout or bandit_result.stderr
    try:
        data = json.loads(bandit_result.stdout)
        metrics = data.get("metrics", {}).get("_totals", {})
        high = int(metrics.get("SEVERITY.HIGH", 0))
        medium = int(metrics.get("SEVERITY.MEDIUM", 0))
        low = int(metrics.get("SEVERITY.LOW", 0))
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    return PulseResult(
        exit_code=pytest_result.returncode,
        stdout=pytest_result.stdout,
        stderr=pytest_result.stderr,
        bandit_output=bandit_output,
        bandit_high=high,
        bandit_medium=medium,
        bandit_low=low,
        bandit_clean=(high == 0),
    )


def make_orchestrator(tmp_path) -> PodmanOrchestrator:
    return PodmanOrchestrator(runner=BanditSubprocessRunner(), work_dir=tmp_path)


# --- Behavior 1: clean code + passing pytest → passed=True ---

def test_clean_passing_code_returns_passed(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    code = "def test_always_passes():\n    assert 1 + 1 == 2\n"

    result = orchestrator.pulse(code)

    assert isinstance(result, PhaseResult)
    assert result.passed is True


# --- Behavior 2: failing pytest + clean bandit → passed=False ---

def test_failing_pytest_returns_not_passed(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    code = "def test_always_fails():\n    assert 1 == 2\n"

    result = orchestrator.pulse(code)

    assert isinstance(result, PhaseResult)
    assert result.passed is False


# --- Behavior 3: subprocess.Popen(shell=True) → bandit HIGH → passed=False even if pytest passes ---

def test_shell_injection_fails_bandit_gate(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    # B602: subprocess_popen_with_shell_equals_true → HIGH severity
    code = (
        "import subprocess\n"
        "def run_cmd(user_input):\n"
        "    subprocess.Popen(user_input, shell=True)\n"
        "def test_passes():\n"
        "    assert True\n"
    )

    result = orchestrator.pulse(code)

    assert result.passed is False
    assert result.error is not None
    assert "Security gate" in result.error


# --- Behavior 4: MEDIUM finding (pickle.loads) is non-blocking ---

def test_medium_finding_does_not_block(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    # B301: pickle.loads → MEDIUM severity, not blocking
    code = (
        "import pickle\n"
        "def load_data(raw):\n"
        "    return pickle.loads(raw)\n"
        "def test_passes():\n"
        "    assert True\n"
    )

    result = orchestrator.pulse(code)

    assert result.passed is True


# --- Behavior 5: PhaseResult carries bandit counts in error on HIGH ---

def test_phase_result_includes_bandit_counts_on_high(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    code = (
        "import subprocess\n"
        "def run_cmd(user_input):\n"
        "    subprocess.Popen(user_input, shell=True)\n"
        "def test_passes():\n"
        "    assert True\n"
    )

    result = orchestrator.pulse(code)

    assert "HIGH=1" in result.error
