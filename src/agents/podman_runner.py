"""
PodmanRunner — production ContainerRunner backed by rootless Podman.

Runs a persistent sidecar container (start once, exec per pulse).
Requires podman in PATH. Tests skip gracefully when podman is absent.
"""
import json
import subprocess
import tempfile
import uuid
from pathlib import Path

from src.agents.podman_orchestrator import ContainerRunner, PulseResult, canonical_hash

_REMOTE_WS = "/tmp/ws"


class PodmanRunner:
    """
    ContainerRunner implementation using rootless Podman.

    Lifecycle:
        runner = PodmanRunner()
        runner.start()          # launches container
        result = runner.send_pulse({"test.py": ..., "impl.py": ...})
        runner.stop()           # removes container
    """

    def __init__(
        self,
        image: str = "localhost/ace-harness:latest",
        container_name: str | None = None,
        cpus: str = "0.5",
        memory: str = "256m",
        test_timeout: int = 10,
    ) -> None:
        self._image = image
        self._name = container_name or f"harness_{uuid.uuid4().hex[:8]}"
        self._cpus = cpus
        self._memory = memory
        self._test_timeout = test_timeout
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
            [
                "podman", "run", "-d",
                "--name", self._name,
                "--network", "none",
                "--cpus", self._cpus,
                "--memory", self._memory,
                self._image, "sleep", "infinity",
            ],
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

    def send_pulse(self, files: dict[str, str]) -> PulseResult:
        # Write files to a host temp dir, then cp the whole directory into the container
        with tempfile.TemporaryDirectory() as local_ws:
            local_ws_path = Path(local_ws)
            for name, content in files.items():
                (local_ws_path / name).write_text(content)

            # Recreate workspace dir inside the container
            subprocess.run(
                ["podman", "exec", self._name, "rm", "-rf", _REMOTE_WS],
                capture_output=True,
            )
            subprocess.run(
                ["podman", "exec", self._name, "mkdir", "-p", _REMOTE_WS],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["podman", "cp", f"{local_ws}/.", f"{self._name}:{_REMOTE_WS}/"],
                check=True,
                capture_output=True,
            )

        pytest_result = subprocess.run(
            ["podman", "exec", self._name,
             "python", "-m", "pytest", _REMOTE_WS, "-v", "--tb=short",
             f"--timeout={self._test_timeout}"],
            capture_output=True,
            text=True,
        )

        bandit_result = subprocess.run(
            ["podman", "exec", self._name,
             "python", "-m", "bandit", "-r", _REMOTE_WS, "--format", "json", "-q"],
            capture_output=True,
            text=True,
        )

        # Read files back from container to compute h_executed from what actually ran
        h_executed = self._compute_remote_hash(list(files.keys()))

        return PulseResult(
            exit_code=pytest_result.returncode,
            stdout=pytest_result.stdout,
            stderr=pytest_result.stderr,
            **_parse_bandit(bandit_result.stdout or bandit_result.stderr),
            h_executed=h_executed,
        )

    def _compute_remote_hash(self, filenames: list[str]) -> str:
        """Read each file from the container workspace and compute canonical_hash."""
        executed_files: dict[str, str] = {}
        for name in filenames:
            result = subprocess.run(
                ["podman", "exec", self._name, "cat", f"{_REMOTE_WS}/{name}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                executed_files[name] = result.stdout
        return canonical_hash(executed_files) if executed_files else ""


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
