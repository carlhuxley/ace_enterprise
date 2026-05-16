"""
PodmanOrchestrator — stateless sidecar execution layer for the Clean Room harness.

Sends code strings to an isolated ContainerRunner, returns a PhaseResult.
Production runner is PodmanRunner (requires podman); SubprocessRunner is the
test double for environments without a container runtime.
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


@runtime_checkable
class ContainerRunner(Protocol):
    def send_pulse(self, code_path: Path) -> PulseResult: ...
    def is_alive(self) -> bool: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...


class PodmanOrchestrator:
    def __init__(self, runner: ContainerRunner, work_dir: Path | None = None) -> None:
        self._runner = runner
        self._work_dir = work_dir or Path(tempfile.mkdtemp(prefix="harness_pulse_"))
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._started = False

    def pulse(self, code: str) -> PhaseResult:
        if not self._started:
            self.start()
        h_proposed = hashlib.sha256(code.encode()).hexdigest()
        code_path = self._work_dir / "pulse_code.py"
        code_path.write_text(code)
        try:
            raw = self._runner.send_pulse(code_path)
        except Exception:
            self.start()
            raw = self._runner.send_pulse(code_path)
        if raw.h_executed and raw.h_executed != h_proposed:
            code_path.unlink(missing_ok=True)
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
