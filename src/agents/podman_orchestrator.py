"""
PodmanOrchestrator — stateless sidecar execution layer for the Clean Room harness.

Sends code to an isolated ContainerRunner, returns a PhaseResult.
Production runner is PodmanRunner (requires podman); SubprocessRunner is the
test double for environments without a container runtime.

pulse() accepts either a string (single-file backward compat) or a
dict[str, str] mapping filename → content for multi-file workspaces.
"""
import hashlib
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from src.agents.language_pod import PhaseResult


class SecurityBreachError(Exception):
    """Raised when H_proposed ≠ H_executed — the container ran different code than was sent."""


@dataclass
class PulseResult:
    """Raw response from the container runner, including bandit analysis."""
    exit_code: int
    stdout: str
    stderr: str
    bandit_output: str = ""
    bandit_high: int = 0
    bandit_medium: int = 0
    bandit_low: int = 0
    bandit_clean: bool = True
    h_executed: str = ""


def canonical_hash(files: dict[str, str]) -> str:
    """Deterministic SHA-256 over a workspace: sorted(filename + content) pairs."""
    manifest = "".join(f"{k}\n{v}" for k, v in sorted(files.items()))
    return hashlib.sha256(manifest.encode()).hexdigest()


@runtime_checkable
class ContainerRunner(Protocol):
    def send_pulse(self, files: dict[str, str]) -> PulseResult: ...
    def is_alive(self) -> bool: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...


class PodmanOrchestrator:
    def __init__(self, runner: ContainerRunner, work_dir: Path | None = None) -> None:
        self._runner = runner
        self._work_dir = work_dir or Path(tempfile.mkdtemp(prefix="harness_pulse_"))
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._started = False

    def pulse(self, files: "dict[str, str] | str") -> PhaseResult:
        if isinstance(files, str):
            files = {"test_pulse.py": files}
        if not self._started:
            self.start()
        h_proposed = canonical_hash(files)
        try:
            raw = self._runner.send_pulse(files)
        except Exception:
            self.start()
            raw = self._runner.send_pulse(files)
        if raw.h_executed and raw.h_executed != h_proposed:
            raise SecurityBreachError(
                f"Hash mismatch: H_proposed={h_proposed} H_executed={raw.h_executed}"
            )
        return self._to_phase_result(raw)

    def _to_phase_result(self, raw: PulseResult) -> PhaseResult:
        pytest_passed = raw.exit_code == 0
        if raw.bandit_high > 0:
            counts = f"HIGH={raw.bandit_high} MEDIUM={raw.bandit_medium} LOW={raw.bandit_low}"
            return PhaseResult(
                passed=False,
                output=raw.stdout,
                error=f"Bandit gate: {counts}\n{raw.bandit_output}",
            )
        return PhaseResult(
            passed=pytest_passed,
            output=raw.stdout,
            error=raw.stderr if not pytest_passed else None,
        )

    def start(self) -> None:
        self._runner.start()
        self._started = True

    def stop(self) -> None:
        self._runner.stop()
        self._started = False
