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
     bounds a crash or runaway loop to a child process. This is the same
     "subprocess, not Podman" milestone GoLanguagePod started at before
     ace_enterprise-jww added full container sandboxing -- see
     docs/adr/004-simulation-pod.md for the follow-up tracked to do the same
     here.
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


class SimulationEnvironmentError(RuntimeError):
    """Raised when the simulation subprocess itself cannot run (e.g. pybullet
    not installed, or it crashed/timed out before producing telemetry)."""


class SimulationOracle:
    """Runs a controller script against a SimulationScenario inside a
    headless (p.DIRECT) PyBullet subprocess and reports whether it satisfies
    a list of MetricBound thresholds.
    """

    def __init__(self, scenario: SimulationScenario, timeout_s: float = 30.0, trace_stride: int = 5) -> None:
        self._scenario = scenario
        self._timeout_s = timeout_s
        self._trace_stride = trace_stride

    @property
    def scenario(self) -> SimulationScenario:
        return self._scenario

    def run(self, controller_code: str, invariants: list[MetricBound]) -> SimulationTelemetry:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ace_sim_pod_") as tmpdir:
            controller_path = Path(tmpdir) / "controller.py"
            controller_path.write_text(controller_code, encoding="utf-8")

            payload = {
                "scenario_path": scenario_path(self._scenario),
                "invariants": [asdict(b) for b in invariants],
                "max_steps": _HARD_STEP_CAP,
                "trace_stride": self._trace_stride,
            }

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

            try:
                result = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                raise SimulationEnvironmentError(
                    f"simulation subprocess produced non-JSON output: {proc.stdout[:500]!r}"
                ) from exc

            return SimulationTelemetry(**result)
