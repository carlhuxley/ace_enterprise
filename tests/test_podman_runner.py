"""Tests for PodmanRunner (ace_enterprise-k3o).

Unit tests run without Podman. Integration tests are skipped when
podman is not in PATH via the shared_podman_runner session fixture.

Lifecycle tests (start/stop) use their own runner instances.
Pulse tests share one container for the whole session.
"""
import hashlib
import shutil
from pathlib import Path

import pytest

from src.agents.podman_orchestrator import ContainerRunner, PodmanOrchestrator
from src.agents.podman_runner import PodmanRunner


def podman_available() -> bool:
    return shutil.which("podman") is not None


skip_no_podman = pytest.mark.skipif(
    not podman_available(),
    reason="podman not in PATH",
)


# ---------------------------------------------------------------------------
# Unit: protocol conformance (no Podman needed)
# ---------------------------------------------------------------------------

def test_podman_runner_satisfies_container_runner_protocol():
    runner = PodmanRunner()
    assert isinstance(runner, ContainerRunner)


def test_is_alive_false_before_start():
    runner = PodmanRunner()
    assert runner.is_alive() is False


def test_custom_image_and_name_stored():
    runner = PodmanRunner(image="python:3.11-slim", container_name="my_runner")
    assert runner._image == "python:3.11-slim"
    assert runner._name == "my_runner"


def test_auto_generated_name_is_unique():
    a = PodmanRunner()
    b = PodmanRunner()
    assert a._name != b._name


# ---------------------------------------------------------------------------
# Integration: lifecycle (own runner per test — these test start/stop itself)
# ---------------------------------------------------------------------------

@skip_no_podman
def test_start_launches_running_container():
    runner = PodmanRunner()
    try:
        runner.start()
        assert runner.is_alive() is True
    finally:
        runner.stop()


@skip_no_podman
def test_stop_removes_container():
    runner = PodmanRunner()
    runner.start()
    runner.stop()
    assert runner.is_alive() is False


# ---------------------------------------------------------------------------
# Integration: pulse behaviours (shared session container)
# ---------------------------------------------------------------------------

def test_send_pulse_passing_code_returns_exit_code_zero(shared_podman_runner, tmp_path):
    code_path = tmp_path / "pulse_code.py"
    code_path.write_text("def test_ping():\n    assert True\n")
    result = shared_podman_runner.send_pulse(code_path)
    assert result.exit_code == 0
    assert "passed" in result.stdout


def test_send_pulse_failing_code_returns_nonzero_exit(shared_podman_runner, tmp_path):
    code_path = tmp_path / "pulse_code.py"
    code_path.write_text("def test_fail():\n    assert 1 == 2\n")
    result = shared_podman_runner.send_pulse(code_path)
    assert result.exit_code != 0


def test_send_pulse_populates_h_executed(shared_podman_runner, tmp_path):
    code = "def test_ping():\n    assert True\n"
    code_path = tmp_path / "pulse_code.py"
    code_path.write_text(code)
    result = shared_podman_runner.send_pulse(code_path)
    expected = hashlib.sha256(code.encode()).hexdigest()
    assert result.h_executed == expected


def test_send_pulse_bandit_flags_shell_injection(shared_podman_runner, tmp_path):
    code_path = tmp_path / "pulse_code.py"
    code_path.write_text(
        "import subprocess\n"
        "def run(cmd):\n"
        "    subprocess.Popen(cmd, shell=True)\n"
        "def test_passes():\n"
        "    assert True\n"
    )
    result = shared_podman_runner.send_pulse(code_path)
    assert result.bandit_high >= 1
    assert not result.bandit_clean


def test_orchestrator_pulse_end_to_end_with_podman_runner(shared_podman_runner, tmp_path):
    """Full Safety Sandwich: ImportFilter → Bandit → HashLock via real container."""
    orchestrator = PodmanOrchestrator(runner=shared_podman_runner, work_dir=tmp_path / "work")
    code = "def test_ping():\n    assert True\n"
    result = orchestrator.pulse(code)
    assert result.passed is True
