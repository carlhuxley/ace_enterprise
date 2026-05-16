"""Tests for Hash-Lock protocol in PodmanOrchestrator (ace_enterprise-2dx)."""
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from src.agents.language_pod import PhaseResult
from src.agents.podman_orchestrator import (
    PodmanOrchestrator,
    PulseResult,
    SecurityBreachError,
)


class HashingSubprocessRunner:
    """Test double: runs pytest + computes h_executed, mimicking container behaviour."""

    def __init__(self):
        self._alive = True

    def send_pulse(self, code_path: Path) -> PulseResult:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(code_path), "-v", "--tb=short"],
            capture_output=True,
            text=True,
        )
        h_executed = hashlib.sha256(code_path.read_bytes()).hexdigest()
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
    return PodmanOrchestrator(runner=HashingSubprocessRunner(), work_dir=tmp_path)


# --- Behavior 1: hashes match → PhaseResult returned normally ---

def test_matching_hashes_return_phase_result(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    code = "def test_ping():\n    assert True\n"

    result = orchestrator.pulse(code)

    assert isinstance(result, PhaseResult)
    assert result.passed is True


# --- Behavior 2: tampered h_executed → SecurityBreachError ---

class TamperingRunner:
    """Returns a deliberately wrong h_executed to simulate container tampering."""

    def send_pulse(self, code_path: Path) -> PulseResult:
        return PulseResult(
            exit_code=0,
            stdout="1 passed",
            stderr="",
            h_executed="deadbeef" * 8,  # wrong hash
        )

    def is_alive(self) -> bool:
        return True

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def test_tampered_hash_raises_security_breach(tmp_path):
    orchestrator = PodmanOrchestrator(runner=TamperingRunner(), work_dir=tmp_path)
    code = "def test_ping():\n    assert True\n"

    with pytest.raises(SecurityBreachError):
        orchestrator.pulse(code)


# --- Behavior 3: SecurityBreachError message includes both hashes ---

def test_security_breach_error_includes_both_hashes(tmp_path):
    orchestrator = PodmanOrchestrator(runner=TamperingRunner(), work_dir=tmp_path)
    code = "def test_ping():\n    assert True\n"

    with pytest.raises(SecurityBreachError, match="H_proposed=") as exc_info:
        orchestrator.pulse(code)

    msg = str(exc_info.value)
    assert "H_proposed=" in msg
    assert "H_executed=" in msg
    assert "deadbeef" in msg


# --- Behavior 4: hashing adds < 5ms overhead ---

def test_hashing_overhead_under_5ms():
    import time
    # A realistic module-sized payload (~10 KB)
    code = "x = 1\n" * 1000
    start = time.perf_counter()
    for _ in range(100):
        hashlib.sha256(code.encode()).hexdigest()
    elapsed_ms = (time.perf_counter() - start) / 100 * 1000
    assert elapsed_ms < 5, f"SHA-256 took {elapsed_ms:.2f}ms per call"
