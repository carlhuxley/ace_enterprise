"""
PodmanRunner — production ContainerRunner backed by rootless Podman.

Runs a persistent sidecar container (start once, exec per pulse).
Requires podman in PATH. Tests skip gracefully when podman is absent.
"""
import json
import subprocess
import uuid
from pathlib import Path

from src.agents.podman_orchestrator import ContainerRunner, PulseResult

_REMOTE_CODE_PATH = "/tmp/pulse_code.py"


class PodmanRunner:
    """
    ContainerRunner implementation using rootless Podman.

    Lifecycle:
        runner = PodmanRunner()
        runner.start()          # launches container, installs deps
        result = runner.send_pulse(path)
        runner.stop()           # removes container
    """

    def __init__(
        self,
        image: str = "localhost/ace-harness:latest",
        container_name: str | None = None,
    ) -> None:
        self._image = image
        self._name = container_name or f"harness_{uuid.uuid4().hex[:8]}"
        self._alive = False

    # ------------------------------------------------------------------
    # ContainerRunner protocol
    # ------------------------------------------------------------------

    def start(self) -> None:
        # Clean up any leftover container from a previous session
        subprocess.run(
            ["podman", "rm", "-f", self._name],
            capture_output=True,
        )
        subprocess.run(
            ["podman", "run", "-d", "--name", self._name, self._image, "sleep", "infinity"],
            check=True,
            capture_output=True,
        )
        self._alive = True

    def stop(self) -> None:
        subprocess.run(
            ["podman", "rm", "-f", self._name],
            capture_output=True,
        )
        self._alive = False

    def is_alive(self) -> bool:
        if not self._alive:
            return False
        result = subprocess.run(
            ["podman", "inspect", self._name, "--format", "{{.State.Status}}"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and "running" in result.stdout

    def send_pulse(self, code_path: Path) -> PulseResult:
        subprocess.run(
            ["podman", "cp", str(code_path), f"{self._name}:{_REMOTE_CODE_PATH}"],
            check=True,
            capture_output=True,
        )

        pytest_result = subprocess.run(
            ["podman", "exec", self._name,
             "python", "-m", "pytest", _REMOTE_CODE_PATH, "-v", "--tb=short"],
            capture_output=True,
            text=True,
        )

        bandit_result = subprocess.run(
            ["podman", "exec", self._name,
             "python", "-m", "bandit", "-r", _REMOTE_CODE_PATH, "--format", "json", "-q"],
            capture_output=True,
            text=True,
        )

        hash_result = subprocess.run(
            ["podman", "exec", self._name,
             "python", "-c",
             f"import hashlib; print(hashlib.sha256(open('{_REMOTE_CODE_PATH}','rb').read()).hexdigest())"],
            capture_output=True,
            text=True,
        )
        h_executed = hash_result.stdout.strip()

        return PulseResult(
            exit_code=pytest_result.returncode,
            stdout=pytest_result.stdout,
            stderr=pytest_result.stderr,
            **_parse_bandit(bandit_result.stdout or bandit_result.stderr),
            h_executed=h_executed,
        )


def _parse_bandit(raw: str) -> dict:
    high = medium = low = 0
    try:
        data = json.loads(raw)
        totals = data.get("metrics", {}).get("_totals", {})
        high = int(totals.get("SEVERITY.HIGH", 0))
        medium = int(totals.get("SEVERITY.MEDIUM", 0))
        low = int(totals.get("SEVERITY.LOW", 0))
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return {
        "bandit_output": raw,
        "bandit_high": high,
        "bandit_medium": medium,
        "bandit_low": low,
        "bandit_clean": high == 0,
    }
