"""
SimulationOracle — a physics-simulation test oracle for SimulationPod.

Where PythonLanguagePod/GoLanguagePod treat pytest/go-test as the execution
oracle, this treats a headless PyBullet simulation as the oracle: a
controller script (the GREEN-phase "implementation") is executed against a
SimulationScenario (src/agents/simulation_scenario.py), and the resulting
telemetry is checked against MetricBound thresholds extracted from a Gherkin
spec (src/agents/simulation_invariants.py).

This module is scenario-agnostic: it holds a SimulationScenario instance
only to read its metadata (default_invariants, default_max_steps,
controller_contract, null_action_source) and its dotted path, and delegates
all physical simulation to simulation_runner.py, run in a subprocess.

Isolation: the simulation runs in a subprocess, not in-process, for two
reasons that mirror the ADR 002 "subprocess vs in-process" rationale for
LanguagePod implementations:
  1. pybullet's DIRECT client is a stateful, process-global C extension --
     running one simulation per subprocess guarantees no state leaks between
     RED/GREEN/REFACTOR invocations.
  2. The controller code is LLM-generated and untrusted. Subprocess isolation
     bounds a crash or runaway loop to a child process.

That bare subprocess is still the default (no podman/image required, matches
every existing test). Passing a `runner` (a SimulationPodmanRunner) instead
graduates execution into the same rootless-Podman sandbox (--network none,
--cap-drop all, read-only workspace) every other pod already runs its
generated code in -- see docs/adr/004-simulation-pod.md.
"""
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from src.agents.simulation_invariants import MetricBound
from src.agents.simulation_runner import SimulationTelemetry
from src.agents.simulation_scenario import SimulationScenario, scenario_path

__all__ = ["SimulationTelemetry", "SimulationEnvironmentError", "SimulationOracle"]

# Absolute ceiling regardless of what a Gherkin spec asks for -- protects the
# subprocess (and its timeout budget) from a runaway extracted step count.
_HARD_STEP_CAP = 5000

_REPO_ROOT = Path(__file__).resolve().parents[2]

# A bandit-HIGH finding must read as a hard abort to TDDCycleRunner (see
# _is_abort()'s "Security gate:" prefix check) -- SimulationPod maps this
# prefix straight through without its usual "SimulationEnvironment: " wrap,
# so it must appear first in the message, verbatim, not be a substring
# somewhere inside a longer sentence.
SECURITY_GATE_PREFIX = "Security gate:"


class SimulationEnvironmentError(RuntimeError):
    """Raised when the simulation subprocess itself cannot run (e.g. pybullet
    not installed, or it crashed/timed out before producing telemetry)."""


class SimulationOracle:
    """Runs a controller script against a SimulationScenario inside a
    headless (p.DIRECT) PyBullet simulation and reports whether it satisfies
    a list of MetricBound thresholds.

    Runs in a bare host subprocess by default. Pass `runner` (a
    SimulationPodmanRunner) to run inside a rootless Podman container
    instead -- same telemetry contract either way, only the transport
    changes. The runner is started lazily on first use and kept alive across
    calls; call close() to tear it down.
    """

    def __init__(
        self,
        scenario: SimulationScenario,
        timeout_s: float = 30.0,
        trace_stride: int = 5,
        runner=None,
    ) -> None:
        self._scenario = scenario
        self._timeout_s = timeout_s
        self._trace_stride = trace_stride
        self._runner = runner
        self._runner_started = False

    @property
    def scenario(self) -> SimulationScenario:
        return self._scenario

    def close(self) -> None:
        if self._runner is not None and self._runner_started:
            self._runner.stop()
            self._runner_started = False

    def run(self, controller_code: str, invariants: list[MetricBound]) -> SimulationTelemetry:
        payload = {
            "scenario_path": scenario_path(self._scenario),
            "invariants": [asdict(b) for b in invariants],
            "max_steps": _HARD_STEP_CAP,
            "trace_stride": self._trace_stride,
        }
        if self._runner is not None:
            return self._run_in_container(controller_code, payload)
        return self._run_in_subprocess(controller_code, payload)

    def _run_in_subprocess(self, controller_code: str, payload: dict) -> SimulationTelemetry:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ace_sim_pod_") as tmpdir:
            controller_path = Path(tmpdir) / "controller.py"
            controller_path.write_text(controller_code, encoding="utf-8")

            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "src.agents.simulation_runner", str(controller_path)],
                    input=json.dumps(payload),
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_s,
                    cwd=str(_REPO_ROOT),
                )
            except subprocess.TimeoutExpired as exc:
                raise SimulationEnvironmentError(
                    f"simulation subprocess timed out after {self._timeout_s}s"
                ) from exc

            if proc.returncode != 0:
                raise SimulationEnvironmentError(
                    f"simulation subprocess exited {proc.returncode}: {proc.stderr.strip()}"
                )

            return self._parse_telemetry(proc.stdout)

    def _run_in_container(self, controller_code: str, payload: dict) -> SimulationTelemetry:
        if not self._runner_started:
            self._runner.start()
            self._runner_started = True

        try:
            raw = self._runner.run_simulation_pulse(controller_code, payload)
        except TimeoutError as exc:
            raise SimulationEnvironmentError(str(exc)) from exc
        except Exception:
            # Mirrors PodmanOrchestrator.pulse()'s own retry-once-on-error:
            # a container that died between pulses is restarted rather than
            # permanently failing every subsequent call in the same pod run.
            self._runner.start()
            raw = self._runner.run_simulation_pulse(controller_code, payload)

        if raw.bandit_high > 0:
            counts = f"HIGH={raw.bandit_high} MEDIUM={raw.bandit_medium} LOW={raw.bandit_low}"
            raise SimulationEnvironmentError(f"{SECURITY_GATE_PREFIX} {counts}\n{raw.bandit_output}")

        if raw.exit_code != 0:
            raise SimulationEnvironmentError(
                f"simulation container exited {raw.exit_code}: {raw.stderr.strip()}"
            )

        return self._parse_telemetry(raw.stdout)

    def _parse_telemetry(self, stdout: str) -> SimulationTelemetry:
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise SimulationEnvironmentError(
                f"simulation run produced non-JSON output: {stdout[:500]!r}"
            ) from exc
        return SimulationTelemetry(**result)
