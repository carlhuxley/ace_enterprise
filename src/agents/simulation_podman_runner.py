"""
SimulationPodmanRunner — PodmanRunner variant for SimulationPod's physics
oracle, graduating it from a bare host subprocess to the same rootless-
Podman sandboxing (--network none, --cap-drop all, read-only workspace,
tmpfs /tmp) every other pod's execution already gets.

Overrides send_pulse() to run simulation_runner.py (instead of pytest) as
`python -m src.agents.simulation_runner` inside the container, piping the
scenario/invariants JSON payload over stdin exactly as SimulationOracle's
bare-subprocess path already does -- only the transport changes, not the
protocol. bandit still runs against the controller code for the same
defense-in-depth reason every other pod's container runs it, even though
ImportFilter already screened the code on the host before it got here.

The trusted oracle code (simulation_runner.py and its direct dependencies)
is baked into the image at build time (see Containerfile.simulation) --
only the untrusted controller script arrives per-pulse, via the read-only
/workspace bind mount PodmanRunner.start() sets up.
"""
import json
import subprocess

from src.agents.podman_orchestrator import PulseResult
from src.agents.podman_runner import PodmanRunner, _parse_bandit

_SIM_WORKDIR = "/opt/ace_sim"
_REMOTE_WS = "/workspace"
_CONTROLLER_FILENAME = "controller.py"


def build_simulation_image(
    containerfile: str = "docker/harness/Containerfile.simulation",
    context: str = ".",
    tag: str = "localhost/ace-sim-harness:latest",
) -> None:
    """Build the simulation harness image. Safe to call repeatedly (no-op if
    up to date). Context is the repo root, not docker/harness/ like the
    other harnesses -- the Containerfile COPYs src/agents/simulation_*.py
    directly, so it needs the real repo-relative paths in its build context."""
    subprocess.run(
        ["podman", "build", "-f", containerfile, "-t", tag, context],
        check=True,
    )


class SimulationPodmanRunner(PodmanRunner):
    """PodmanRunner pre-configured for the simulation harness image."""

    def __init__(
        self,
        container_name: str | None = None,
        cpus: str = "1.0",
        memory: str = "512m",
        # Wall-clock budget for one simulation_runner.py invocation inside the
        # container -- SimulationOracle's own `timeout_s` is the natural
        # source for this (a physics run legitimately takes longer than a
        # pytest collection), so callers should pass that through rather than
        # accepting this default.
        sim_timeout: float = 30.0,
    ) -> None:
        super().__init__(
            image="localhost/ace-sim-harness:latest",
            container_name=container_name,
            cpus=cpus,
            memory=memory,
        )
        self._sim_timeout = sim_timeout

    def send_pulse(self, files: dict[str, str]) -> PulseResult:
        """`files` must contain exactly one entry: the controller script,
        keyed by any name (SimulationOracle always sends "controller.py").
        The scenario/invariants JSON payload isn't a file -- it's piped over
        the podman exec's stdin, matching how the bare-subprocess path in
        simulation_oracle.py already invokes simulation_runner.py."""
        raise NotImplementedError(
            "SimulationPodmanRunner uses run_simulation_pulse(), not the generic "
            "files-only send_pulse() -- it needs a JSON args payload the "
            "ContainerRunner protocol has no slot for."
        )

    def run_simulation_pulse(self, controller_code: str, args_payload: dict) -> PulseResult:
        for existing in self._host_ws.iterdir():
            if existing.is_dir():
                import shutil
                shutil.rmtree(existing)
            else:
                existing.unlink()
        (self._host_ws / _CONTROLLER_FILENAME).write_text(controller_code)

        try:
            sim_proc = subprocess.run(
                [
                    "podman", "exec", "-i", "--workdir", _SIM_WORKDIR, self._name,
                    "python", "-m", "src.agents.simulation_runner",
                    f"{_REMOTE_WS}/{_CONTROLLER_FILENAME}",
                ],
                input=json.dumps(args_payload),
                capture_output=True,
                text=True,
                timeout=self._sim_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"simulation subprocess timed out after {self._sim_timeout}s") from exc

        bandit_result = subprocess.run(
            ["podman", "exec", self._name, "python", "-m", "bandit", "-r", _REMOTE_WS, "--format", "json", "-q"],
            capture_output=True,
            text=True,
        )

        h_executed = self._compute_workspace_hash([_CONTROLLER_FILENAME])

        return PulseResult(
            exit_code=sim_proc.returncode,
            stdout=sim_proc.stdout,
            stderr=sim_proc.stderr,
            **_parse_bandit(bandit_result.stdout or bandit_result.stderr),
            h_executed=h_executed,
        )
