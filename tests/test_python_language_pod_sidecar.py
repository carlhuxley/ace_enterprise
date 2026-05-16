"""Tests for PythonLanguagePod wired to PodmanOrchestrator (ace_enterprise-jz8).

All tests exercise the from_worker() construction path only.
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
    """Runs pytest on host + returns h_executed, mimicking sidecar behaviour."""

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
# Fixtures
# ---------------------------------------------------------------------------

PASSING_CODE = (
    "def add(a, b):\n"
    "    return a + b\n"
    "def test_add():\n"
    "    assert add(1, 2) == 3\n"
)

FAILING_CODE = (
    "def add(a, b):\n"
    "    return 0  # wrong\n"
    "def test_add():\n"
    "    assert add(1, 2) == 3\n"
)

FORBIDDEN_CODE = (
    "import os\n"
    "def add(a, b):\n"
    "    return a + b\n"
    "def test_add():\n"
    "    assert add(1, 2) == 3\n"
)


def make_worker(impl_code: str = PASSING_CODE) -> MagicMock:
    worker = MagicMock()
    worker.llm_client = MagicMock()
    worker.llm_client.generate.return_value = {"content": "", "tokens_used": 10}
    worker.generate_implementation.return_value = impl_code
    worker.generate_test.return_value = impl_code
    return worker


def make_pod(tmp_path: Path, runner=None, impl_code: str = PASSING_CODE) -> tuple[PythonLanguagePod, PodSpec]:
    runner = runner or HashingSubprocessRunner()
    orchestrator = PodmanOrchestrator(
        runner=runner,
        work_dir=tmp_path / "sidecar",
    )
    worker = make_worker(impl_code)
    pod = PythonLanguagePod.from_worker(worker, tmp_path, orchestrator)
    spec = PodSpec(
        feature_requirement="add two numbers",
        test_file=tmp_path / "tests" / "test_add.py",
        implementation_file=tmp_path / "src" / "add.py",
        cycle_number=1,
    )
    return pod, spec


# ---------------------------------------------------------------------------
# Behavior 1: clean code → passed=True + impl file committed (tracer bullet)
# ---------------------------------------------------------------------------

def test_green_clean_code_returns_passed_and_commits_file(tmp_path):
    pod, spec = make_pod(tmp_path)

    result = pod.run_green(spec)

    assert isinstance(result, PhaseResult)
    assert result.passed is True
    assert spec.implementation_file.exists()
    assert "add" in spec.implementation_file.read_text()


# ---------------------------------------------------------------------------
# Behavior 2: pytest fails → passed=False + impl file NOT committed
# ---------------------------------------------------------------------------

def test_green_failing_pytest_does_not_commit_file(tmp_path):
    pod, spec = make_pod(tmp_path, impl_code=FAILING_CODE)

    result = pod.run_green(spec)

    assert result.passed is False
    assert not spec.implementation_file.exists()


# ---------------------------------------------------------------------------
# Behavior 4: hash mismatch → passed=False, "SecurityBreach" in error, no commit
# ---------------------------------------------------------------------------

def test_green_hash_mismatch_surfaces_as_failed_phase_result(tmp_path):
    pod, spec = make_pod(tmp_path, runner=TamperingRunner())

    result = pod.run_green(spec)

    assert result.passed is False
    assert result.error is not None
    assert "SecurityBreach" in result.error
    assert not spec.implementation_file.exists()


# ---------------------------------------------------------------------------
# Behavior 5: commit_to_disk is atomic — no .tmp left behind, dst is correct
# ---------------------------------------------------------------------------

def test_commit_to_disk_is_atomic(tmp_path):
    from src.agents.python_language_pod import commit_to_disk

    dst = tmp_path / "subdir" / "output.py"
    code = "x = 42\n"

    commit_to_disk(code, dst)

    assert dst.exists()
    assert dst.read_text() == code
    assert not (tmp_path / "subdir" / "output.tmp").exists()


# ---------------------------------------------------------------------------
# Behavior 3: forbidden import → passed=False, "Forbidden" in error, no commit
# ---------------------------------------------------------------------------

def test_green_forbidden_import_surfaces_as_failed_phase_result(tmp_path):
    pod, spec = make_pod(tmp_path, impl_code=FORBIDDEN_CODE)

    result = pod.run_green(spec)

    assert result.passed is False
    assert result.error is not None
    assert "Forbidden" in result.error
    assert not spec.implementation_file.exists()
