"""Tests for PodmanRunner (ace_enterprise-k3o).

Unit tests run without Podman. Integration tests are skipped when
podman is not in PATH via the shared_podman_runner session fixture.

Lifecycle tests (start/stop) use their own runner instances.
Pulse tests share one container for the whole session.
"""
import shutil

import pytest

from src.agents.podman_orchestrator import ContainerRunner, PodmanOrchestrator, canonical_hash
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
    files = {"test_ping.py": "def test_ping():\n    assert True\n"}
    result = shared_podman_runner.send_pulse(files)
    assert result.exit_code == 0
    assert "passed" in result.stdout


def test_send_pulse_failing_code_returns_nonzero_exit(shared_podman_runner, tmp_path):
    files = {"pulse_code.py": "def test_fail():\n    assert 1 == 2\n"}
    result = shared_podman_runner.send_pulse(files)
    assert result.exit_code != 0


def test_send_pulse_populates_h_executed(shared_podman_runner, tmp_path):
    files = {"pulse_code.py": "def test_ping():\n    assert True\n"}
    result = shared_podman_runner.send_pulse(files)
    expected = canonical_hash(files)
    assert result.h_executed == expected


def test_send_pulse_bandit_flags_shell_injection(shared_podman_runner, tmp_path):
    files = {
        "pulse_code.py": (
            "import subprocess\n"
            "def run(cmd):\n"
            "    subprocess.Popen(cmd, shell=True)\n"
            "def test_passes():\n"
            "    assert True\n"
        )
    }
    result = shared_podman_runner.send_pulse(files)
    assert result.bandit_high >= 1
    assert not result.bandit_clean


def test_orchestrator_pulse_end_to_end_with_podman_runner(shared_podman_runner, tmp_path):
    """Full Safety Sandwich: ImportFilter → Bandit → HashLock via real container."""
    orchestrator = PodmanOrchestrator(runner=shared_podman_runner, work_dir=tmp_path / "work")
    code = "def test_ping():\n    assert True\n"
    result = orchestrator.pulse(code)
    assert result.passed is True


def test_multi_file_cross_import_in_container(shared_podman_runner, tmp_path):
    """Impl and test as separate files — test imports from impl module."""
    files = {
        "add.py": "def add(a, b):\n    return a + b\n",
        "test_add.py": "from add import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
    }
    result = shared_podman_runner.send_pulse(files)
    assert result.exit_code == 0
    assert "passed" in result.stdout


# ---------------------------------------------------------------------------
# writable_workdir: validation runners can do relative-path disk I/O
# ---------------------------------------------------------------------------

_RELATIVE_WRITE_TEST = {
    "test_write.py": (
        "import json\n"
        "from pathlib import Path\n"
        "def test_relative_write_and_read_back():\n"
        "    p = Path('scratch_manifest.json')\n"
        "    p.write_text(json.dumps({'ok': True}))\n"
        "    assert json.loads(p.read_text()) == {'ok': True}\n"
    )
}


def test_unit_writable_workdir_defaults_false():
    assert PodmanRunner()._writable_workdir is False
    assert PodmanRunner(writable_workdir=True)._writable_workdir is True


@skip_no_podman
def test_relative_write_fails_on_default_readonly_workdir():
    runner = PodmanRunner(container_name="harness_ro_workdir_test", test_timeout=20)
    runner.start()
    try:
        result = runner.send_pulse(_RELATIVE_WRITE_TEST)
        assert result.exit_code != 0
        assert "Read-only file system" in result.stdout or "Errno 30" in result.stdout
    finally:
        runner.stop()


@skip_no_podman
def test_relative_write_succeeds_with_writable_workdir():
    runner = PodmanRunner(
        container_name="harness_rw_workdir_test", test_timeout=20, writable_workdir=True
    )
    runner.start()
    try:
        result = runner.send_pulse(_RELATIVE_WRITE_TEST)
        assert result.exit_code == 0, result.stdout
        assert "passed" in result.stdout
    finally:
        runner.stop()
