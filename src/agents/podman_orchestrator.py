"""
PodmanOrchestrator — stateless sidecar execution layer for the Clean Room harness.

Sends code strings to an isolated ContainerRunner, returns pytest results.
Production runner is PodmanRunner (requires podman); SubprocessRunner is the
test double for environments without a container runtime.
"""
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class PulseResult:
    exit_code: int
    stdout: str
    stderr: str


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
        self._started = False

    def pulse(self, code: str) -> PulseResult:
        if not self._started:
            self.start()
        code_path = self._work_dir / "pulse_code.py"
        code_path.write_text(code)
        try:
            return self._runner.send_pulse(code_path)
        except Exception:
            self.start()
            return self._runner.send_pulse(code_path)

    def start(self) -> None:
        self._runner.start()
        self._started = True

    def stop(self) -> None:
        self._runner.stop()
        self._started = False
