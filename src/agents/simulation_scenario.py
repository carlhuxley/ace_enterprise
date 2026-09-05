"""
SimulationScenario — the pluggable physical-world contract SimulationOracle
runs against.

SimulationOracle (src/agents/simulation_oracle.py) and simulation_runner.py
(the subprocess entrypoint that actually steps PyBullet) know nothing about
pegs, holes, fruit, or trajectories -- they only know how to load a scenario
by dotted path, step it, and check the metric trace it produces against
MetricBound thresholds (src/agents/simulation_invariants.py). Everything
physical -- what bodies exist, what a controller action means, which named
metrics are reported -- lives in one scenario class under
src/agents/simulation_scenarios/.

Scenario methods receive `p` (the pybullet module) and `client` (its
connection id) as arguments rather than importing pybullet themselves, so a
scenario class can be instantiated and introspected (default_invariants(),
controller_contract()) in a process that never imports pybullet at all --
only simulation_runner.py, running inside the isolated subprocess, needs it.
"""
import importlib
from typing import Any, Protocol

from src.agents.simulation_invariants import MetricBound

__all__ = ["SimulationScenario", "load_scenario"]


class SimulationScenario(Protocol):
    """One physical task, built and stepped inside a PyBullet DIRECT client."""

    def configure(self, invariants: list[MetricBound]) -> None:
        """Adjust the physical setup from spec'd thresholds before build()
        (e.g. size a socket's clearance from a radial_error tolerance).
        A scenario with nothing to adjust implements this as a no-op."""
        ...

    def build(self, p: Any, client: int) -> None:
        """Construct every body in the world (fixtures, actuator, workpiece)."""
        ...

    def observe(self, p: Any, client: int, step: int, max_steps: int) -> dict[str, float]:
        """Return this step's full observation: ground-truth physical
        readings plus any context the scenario needs. Handed to metrics()
        for grading and to controller_view() to derive what the controller
        actually sees -- not necessarily handed to the controller directly."""
        ...

    def metrics(self, observation: dict[str, float]) -> dict[str, float]:
        """Map a full (ground-truth) observation to the named metrics a
        Gherkin spec can bound. Always sees the real observation, regardless
        of what controller_view() hides from the controller -- the oracle
        must grade on truth even when the controller can't perceive it."""
        ...

    def controller_view(self, observation: dict[str, float]) -> dict[str, float]:
        """Derive what the controller actually perceives from the full
        observation. A scenario with nothing to hide returns `observation`
        unchanged; a scenario modeling imperfect/partial sensing (e.g. a
        force/torque sensor plus a miscalibrated position estimate, with no
        ground-truth coordinates) returns a reduced or corrupted dict here
        instead. This is the only place perception can differ from truth --
        metrics() above always grades on the real observation."""
        ...

    def apply_action(self, p: Any, client: int, action: dict[str, float]) -> None:
        """Apply the controller's action dict to the world. The runner calls
        p.stepSimulation() immediately after this returns."""
        ...

    def null_action_source(self) -> str:
        """Python source for a trivial 'do nothing' controller module, used
        by SimulationPod's RED phase to prove the oracle fails a scenario
        with no real control logic yet."""
        ...

    def default_invariants(self) -> list[MetricBound]:
        """Fallback bounds used when a Gherkin spec declares none."""
        ...

    def default_max_steps(self) -> int:
        """Step budget used when no convergence bound declares one."""
        ...

    def controller_contract(self) -> str:
        """Human-readable observation/action contract, embedded in LLM prompts."""
        ...


def load_scenario(dotted_path: str) -> SimulationScenario:
    """Load a scenario by "module.path:ClassName", e.g.
    "src.agents.simulation_scenarios.peg_in_hole:PegInHoleScenario"."""
    module_path, _, class_name = dotted_path.partition(":")
    if not class_name:
        raise ValueError(f"scenario path must be 'module:ClassName', got {dotted_path!r}")
    module = importlib.import_module(module_path)
    scenario_cls = getattr(module, class_name)
    return scenario_cls()


def scenario_path(scenario: SimulationScenario) -> str:
    """The dotted path load_scenario() can use to reconstruct this scenario
    (e.g. inside the simulation_runner.py subprocess)."""
    cls = type(scenario)
    return f"{cls.__module__}:{cls.__qualname__}"
