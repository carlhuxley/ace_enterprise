"""Tests for multi-file pulse interface (ace_enterprise-pz5).

Verifies that pulse() accepts dict[str, str] mapping filename → content,
writes all files to a shared workspace, and runs pytest across them.
This allows test + impl to be separate files with real cross-module imports.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from src.agents.language_pod import PhaseResult
from src.agents.podman_orchestrator import (
    PodmanOrchestrator,
    PulseResult,
    SecurityBreachError,
    canonical_hash,
)


class WorkspaceSubprocessRunner:
    """Test double: writes files to a temp workspace and runs pytest on the dir."""

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


def make_orchestrator(tmp_path) -> PodmanOrchestrator:
    return PodmanOrchestrator(runner=WorkspaceSubprocessRunner(), work_dir=tmp_path)


# --- Behavior 1: single-file dict works (tracer bullet) ---

def test_single_file_dict_returns_passed(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    result = orchestrator.pulse({"test_ping.py": "def test_ping(): assert True\n"})
    assert isinstance(result, PhaseResult)
    assert result.passed is True


# --- Behavior 2: backward-compat string still accepted ---

def test_string_arg_still_accepted(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    result = orchestrator.pulse("def test_ping(): assert True\n")
    assert result.passed is True


# --- Behavior 3: cross-module import works when impl is a separate file ---

def test_cross_module_import_between_files(tmp_path):
    impl = "def add(a, b):\n    return a + b\n"
    test = "from add import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    orchestrator = make_orchestrator(tmp_path)
    result = orchestrator.pulse({"add.py": impl, "test_add.py": test})
    assert result.passed is True


# --- Behavior 4: failing test in multi-file returns passed=False ---

def test_multi_file_failure_returns_not_passed(tmp_path):
    impl = "def add(a, b):\n    return a - b  # bug\n"
    test = "from add import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    orchestrator = make_orchestrator(tmp_path)
    result = orchestrator.pulse({"add.py": impl, "test_add.py": test})
    assert result.passed is False


# --- Behavior 5: hash mismatch raises SecurityBreachError for multi-file ---

class MultiFileTamperingRunner:
    """Returns wrong h_executed regardless of file count."""

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


def test_multi_file_tamper_raises_security_breach(tmp_path):
    orchestrator = PodmanOrchestrator(runner=MultiFileTamperingRunner(), work_dir=tmp_path)
    files = {"add.py": "def add(a,b): return a+b\n", "test_add.py": "def test_x(): pass\n"}
    with pytest.raises(SecurityBreachError):
        orchestrator.pulse(files)
