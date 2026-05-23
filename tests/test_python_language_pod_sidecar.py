"""Tests for PythonLanguagePod wired to PodmanOrchestrator (ace_enterprise-jz8).

All tests exercise the from_worker() construction path only.
Test and impl are kept as separate files — the worker generates each in isolation
and the orchestrator runs them together in one workspace.
"""
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.agents.language_pod import PhaseResult, PodSpec
from src.agents.podman_orchestrator import PodmanOrchestrator, PulseResult, canonical_hash
from src.agents.python_language_pod import PythonLanguagePod


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class HashingSubprocessRunner:
    """Runs pytest on a workspace dir + returns canonical h_executed."""

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
            h_executed = canonical_hash(
                {name: (ws_path / name).read_text() for name in files}
            )
        return PulseResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            h_executed=h_executed,
        )

    def is_alive(self) -> bool:
        return self._alive

    def start(self) -> None:
        self._alive = True

    def stop(self) -> None:
        self._alive = False


class TamperingRunner:
    """Returns a wrong h_executed to simulate container tampering."""

    def send_pulse(self, files: dict[str, str]) -> PulseResult:
        return PulseResult(
            exit_code=0,
            stdout="1 passed",
            stderr="",
            h_executed="deadbeef" * 8,
        )

    def is_alive(self) -> bool:
        return True

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

IMPL_ONLY = "def add(a, b):\n    return a + b\n"
TEST_ONLY = "from add import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
IMPL_WRONG = "def add(a, b):\n    return 0\n"
IMPL_FORBIDDEN = "import os\n\ndef add(a, b):\n    return a + b\n"


def make_worker(impl_code: str = IMPL_ONLY, test_code: str = TEST_ONLY) -> MagicMock:
    worker = MagicMock()
    worker.llm_client = MagicMock()
    worker.llm_client.generate.return_value = {"content": "", "tokens_used": 10}
    worker.generate_implementation.return_value = impl_code
    worker.generate_test.return_value = test_code
    worker.generate_refactor.return_value = impl_code
    return worker


def make_spec(tmp_path: Path) -> PodSpec:
    return PodSpec(
        feature_requirement="add two numbers",
        test_file=tmp_path / "tests" / "test_add.py",
        implementation_file=tmp_path / "src" / "add.py",
        cycle_number=1,
    )


def make_pod(tmp_path: Path, runner=None, impl_code: str = IMPL_ONLY) -> tuple[PythonLanguagePod, PodSpec]:
    runner = runner or HashingSubprocessRunner()
    orchestrator = PodmanOrchestrator(runner=runner, work_dir=tmp_path / "sidecar")
    worker = make_worker(impl_code=impl_code)
    pod = PythonLanguagePod(worker, tmp_path, orchestrator)
    return pod, make_spec(tmp_path)


def write_test_file(spec: PodSpec, content: str = TEST_ONLY) -> None:
    """Simulate the RED phase having committed the test file."""
    spec.test_file.parent.mkdir(parents=True, exist_ok=True)
    spec.test_file.write_text(content)


def write_impl_file(spec: PodSpec, content: str = IMPL_ONLY) -> None:
    spec.implementation_file.parent.mkdir(parents=True, exist_ok=True)
    spec.implementation_file.write_text(content)


# ---------------------------------------------------------------------------
# GREEN: test file on disk + impl from worker → cross-module import (tracer)
# ---------------------------------------------------------------------------

def test_green_uses_test_file_from_disk_with_separate_impl(tmp_path):
    pod, spec = make_pod(tmp_path)
    write_test_file(spec)

    result = pod.run_green(spec)

    assert isinstance(result, PhaseResult)
    assert result.passed is True
    assert spec.implementation_file.exists()
    assert "add" in spec.implementation_file.read_text()


# ---------------------------------------------------------------------------
# GREEN: wrong impl → test fails → not committed
# ---------------------------------------------------------------------------

def test_green_failing_impl_not_committed(tmp_path):
    pod, spec = make_pod(tmp_path, impl_code=IMPL_WRONG)
    write_test_file(spec)

    result = pod.run_green(spec)

    assert result.passed is False
    assert not spec.implementation_file.exists()


# ---------------------------------------------------------------------------
# GREEN: forbidden import in impl → rejected before reaching orchestrator
# ---------------------------------------------------------------------------

def test_green_forbidden_import_in_impl_surfaces_as_failed(tmp_path):
    pod, spec = make_pod(tmp_path, impl_code=IMPL_FORBIDDEN)
    write_test_file(spec)

    result = pod.run_green(spec)

    assert result.passed is False
    assert result.error is not None
    assert "Forbidden" in result.error
    assert not spec.implementation_file.exists()


# ---------------------------------------------------------------------------
# GREEN: hash mismatch → SecurityBreach error, no commit
# ---------------------------------------------------------------------------

def test_green_hash_mismatch_surfaces_as_failed_phase_result(tmp_path):
    pod, spec = make_pod(tmp_path, runner=TamperingRunner())
    write_test_file(spec)

    result = pod.run_green(spec)

    assert result.passed is False
    assert result.error is not None
    assert "SecurityBreach" in result.error
    assert not spec.implementation_file.exists()


# ---------------------------------------------------------------------------
# REFACTOR: uses both files from disk, runs them together
# ---------------------------------------------------------------------------

def test_refactor_runs_test_and_impl_together(tmp_path):
    pod, spec = make_pod(tmp_path)
    write_test_file(spec)
    write_impl_file(spec)

    result = pod.run_refactor(spec)

    assert isinstance(result, PhaseResult)
    assert result.passed is True


# ---------------------------------------------------------------------------
# RED: names test file correctly (spec.test_file.name, not test_pulse.py)
# ---------------------------------------------------------------------------

def test_red_commits_test_file_to_spec_path(tmp_path):
    pod, spec = make_pod(tmp_path)

    pod.run_red(spec)

    assert spec.test_file.exists()


# ---------------------------------------------------------------------------
# commit_to_disk: atomic write — no .tmp left behind
# ---------------------------------------------------------------------------

def test_commit_to_disk_is_atomic(tmp_path):
    from src.agents.python_language_pod import commit_to_disk

    dst = tmp_path / "subdir" / "output.py"
    commit_to_disk("x = 42\n", dst)

    assert dst.exists()
    assert dst.read_text() == "x = 42\n"
    assert not (tmp_path / "subdir" / "output.tmp").exists()
