"""Tests for PodmanOrchestrator (ace_enterprise-2j2)."""
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from src.agents.language_pod import PhaseResult
from src.agents.podman_orchestrator import ContainerRunner, PodmanOrchestrator, PulseResult


class SubprocessRunner:
    """Test double: runs pytest directly on the host, no container needed."""

    def __init__(self):
        self._alive = True

    def send_pulse(self, files: dict[str, str]) -> PulseResult:
        with tempfile.TemporaryDirectory() as ws:
            ws_path = Path(ws)
            for name, content in files.items():
                (ws_path / name).write_text(content)
            result = subprocess.run(
                [sys.executable, "-m", "pytest", ws, "-v", "--tb=short"],
                capture_output=True,
                text=True,
            )
        return PulseResult(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)

    def is_alive(self) -> bool:
        return self._alive

    def start(self) -> None:
        self._alive = True

    def stop(self) -> None:
        self._alive = False


def make_orchestrator(tmp_path) -> PodmanOrchestrator:
    return PodmanOrchestrator(runner=SubprocessRunner(), work_dir=tmp_path)


# --- Behavior 1: passing code returns passed=True ---

def test_pulse_passing_code_returns_success(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    code = "def test_always_passes():\n    assert 1 + 1 == 2\n"

    result = orchestrator.pulse(code)

    assert isinstance(result, PhaseResult)
    assert result.passed is True
    assert "passed" in result.output


# --- Behavior 2: failing test returns passed=False with failure detail ---

def test_pulse_failing_code_returns_failure(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    code = "def test_always_fails():\n    assert 1 == 2\n"

    result = orchestrator.pulse(code)

    assert isinstance(result, PhaseResult)
    assert result.passed is False
    assert "failed" in result.output.lower()


# --- Behavior 3: auto-start on first pulse without explicit start() ---

def test_pulse_auto_starts_runner(tmp_path):
    runner = SubprocessRunner()
    runner.stop()  # explicitly not started
    orchestrator = PodmanOrchestrator(runner=runner, work_dir=tmp_path)

    code = "def test_ping():\n    assert True\n"
    result = orchestrator.pulse(code)

    assert result.passed is True
    assert runner.is_alive()


# --- Behavior 4: dead runner is restarted and pulse succeeds ---

class DyingRunner:
    """Runner that dies after the first pulse, then recovers on restart."""

    def __init__(self):
        self._alive = True
        self._pulse_count = 0

    def send_pulse(self, files: dict[str, str]) -> PulseResult:
        self._pulse_count += 1
        if self._pulse_count == 1:
            self._alive = False
            raise RuntimeError("sidecar died")
        with tempfile.TemporaryDirectory() as ws:
            ws_path = Path(ws)
            for name, content in files.items():
                (ws_path / name).write_text(content)
            result = subprocess.run(
                [sys.executable, "-m", "pytest", ws, "-v", "--tb=short"],
                capture_output=True,
                text=True,
            )
        return PulseResult(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)

    def is_alive(self) -> bool:
        return self._alive

    def start(self) -> None:
        self._alive = True

    def stop(self) -> None:
        self._alive = False


def test_pulse_recovers_from_dead_runner(tmp_path):
    runner = DyingRunner()
    orchestrator = PodmanOrchestrator(runner=runner, work_dir=tmp_path)

    code = "def test_survives():\n    assert True\n"
    result = orchestrator.pulse(code)

    assert result.passed is True
    assert runner.is_alive()
