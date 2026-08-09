"""
PodmanRunner — production ContainerRunner backed by rootless Podman.

Hot sandbox: one persistent container per session (podman run -d sleep infinity).
Workspace is a host-side directory bind-mounted into the container at /workspace.
On Linux the host directory lives under /dev/shm (tmpfs), so file writes from the
host are instantly visible inside the container with zero copy overhead.
Tests skip gracefully when podman is absent.
"""
import json
import shutil
import subprocess
import uuid
from pathlib import Path

from src.agents.podman_orchestrator import ContainerRunner, PulseResult, canonical_hash

_REMOTE_WS = "/workspace"


class PodmanRunner:
    """
    ContainerRunner implementation using rootless Podman.

    Lifecycle:
        runner = PodmanRunner()
        runner.start()          # launches container with tmpfs workspace mounted
        result = runner.send_pulse({"test.py": ..., "impl.py": ...})
        runner.stop()           # removes container and workspace
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
        self._host_ws: Path | None = None

    # ------------------------------------------------------------------
    # ContainerRunner protocol
    # ------------------------------------------------------------------

    def start(self) -> None:
        # Host-side workspace: prefer /dev/shm (always tmpfs), fall back to /tmp
        shm = Path("/dev/shm")
        base = shm if shm.is_dir() else Path("/tmp")
        self._host_ws = base / f"ace_ws_{self._name}"
        if self._host_ws.exists():
            shutil.rmtree(self._host_ws)
        self._host_ws.mkdir(parents=True)
        # World-readable/executable so the container's non-root (or capability-
        # dropped root) user can read workspace files despite the uid remap from
        # rootless Podman's user namespace. The workspace mount itself is read-only
        # (see -v ...:ro below) so the write bit no longer does anything for the
        # container; left permissive since the host process still needs full
        # access to clear/rewrite the workspace between pulses.
        self._host_ws.chmod(0o777)

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
                # tini-based init reaps zombie child processes (esbuild, node forks)
                # so they don't accumulate and saturate the process table.
                "--init",
                # Drop every ambient capability and block acquiring new ones. Without
                # this, retained caps like CAP_SYS_ADMIN would let generated code
                # remount a read-only workspace mount as read-write from inside.
                "--cap-drop", "all",
                "--security-opt", "no-new-privileges",
                # Bind-mount the host tmpfs dir as the container workspace, read-only.
                # Generated code can read its own test/impl files but can't rewrite
                # them mid-run to fake a pass; canonical_hash pulse verification
                # (podman_orchestrator.py) is defense-in-depth on top of this, not
                # the primary control. The host still has full write access to the
                # same directory outside the container's mount view, so send_pulse()
                # can keep clearing/repopulating it between pulses as before.
                "-v", f"{self._host_ws}:{_REMOTE_WS}:z,ro",
                # Container's own /tmp on RAM too
                "--mount", "type=tmpfs,dst=/tmp",
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
        if self._host_ws and self._host_ws.exists():
            shutil.rmtree(self._host_ws, ignore_errors=True)
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
        # Clear workspace then write exactly the pulse's files directly to the
        # bind-mounted host path — visible in the container immediately, no copy.
        for existing in self._host_ws.iterdir():
            if existing.is_dir():
                shutil.rmtree(existing)
            else:
                existing.unlink()
        for name, content in files.items():
            (self._host_ws / name).write_text(content)

        pytest_result = subprocess.run(
            [
                "podman", "exec", "--workdir", _REMOTE_WS, self._name,
                # -B: don't write __pycache__/.pyc; -p no:cacheprovider: don't
                # write .pytest_cache — the workspace mount is now read-only.
                "python", "-B", "-m", "pytest", _REMOTE_WS, "-v", "--tb=short",
                f"--timeout={self._test_timeout}", "-p", "no:cacheprovider",
            ],
            capture_output=True,
            text=True,
        )

        # Runs AFTER pytest, not before (ace_enterprise-rli) — by the time a
        # HIGH finding aborts the cycle (podman_orchestrator.py's Security
        # gate), the code has already executed once inside the container.
        # This is a commit-time/retry gate, not a pre-execution check; the
        # actual containment is --network none + the read-only workspace
        # mount (start(), above), not Bandit.
        bandit_result = subprocess.run(
            [
                "podman", "exec", self._name,
                "python", "-m", "bandit", "-r", _REMOTE_WS,
                "--format", "json", "-q",
            ],
            capture_output=True,
            text=True,
        )

        # Hash computed from host-side files (same bytes as container via bind mount)
        h_executed = self._compute_workspace_hash(list(files.keys()))

        return PulseResult(
            exit_code=pytest_result.returncode,
            stdout=pytest_result.stdout,
            stderr=pytest_result.stderr,
            **_parse_bandit(bandit_result.stdout or bandit_result.stderr),
            h_executed=h_executed,
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _compute_workspace_hash(self, filenames: list[str]) -> str:
        """Read the named files from the host workspace and compute canonical_hash."""
        executed: dict[str, str] = {}
        for name in filenames:
            path = self._host_ws / name
            if path.exists():
                executed[name] = path.read_text()
        return canonical_hash(executed) if executed else ""


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
