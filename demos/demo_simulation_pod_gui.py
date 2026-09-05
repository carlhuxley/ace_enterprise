"""
Demo: Watch SimulationPod's physics oracle in PyBullet's GUI

SimulationPod (src/agents/simulation_pod.py) always runs headless (p.DIRECT)
so it can execute inside a subprocess -- there is nothing to look at when
TDDCycleRunner drives it. This script runs the exact same
SimulationScenario.build/observe/metrics/apply_action calls
simulation_runner.py uses, but against a real p.GUI window with a
hand-written controller, so you can watch a run happen.

Usage:
    .venv/bin/python demos/demo_simulation_pod_gui.py                # peg-in-hole
    .venv/bin/python demos/demo_simulation_pod_gui.py --scenario trajectory
    .venv/bin/python demos/demo_simulation_pod_gui.py --controller null  # watch it fail
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pybullet as p  # noqa: E402

from src.agents.simulation_runner import check_final, check_instantaneous  # noqa: E402
from src.agents.simulation_scenarios.peg_in_hole import PegInHoleScenario  # noqa: E402
from src.agents.simulation_scenarios.trajectory_following import (  # noqa: E402
    TrajectoryFollowingScenario,
)

TIME_STEP_S = 1.0 / 240.0


def peg_controller(observation):
    """The same hand-verified controller used in smoke-testing PegInHoleScenario:
    align radially to the hole center, then descend."""
    kp = 2.0
    x, y = observation["x"], observation["y"]
    radial = (x**2 + y**2) ** 0.5
    vz = -0.03 if radial <= 0.001 else -0.005
    return {"vx": -kp * x, "vy": -kp * y, "vz": vz}


def trajectory_controller(observation):
    """The same hand-verified controller used in smoke-testing
    TrajectoryFollowingScenario: proportional pursuit of the moving target."""
    kp = 10.0
    dx = observation["target_x"] - observation["x"]
    dy = observation["target_y"] - observation["y"]
    dz = observation["target_z"] - observation["z"]
    return {"vx": kp * dx, "vy": kp * dy, "vz": kp * dz}


def null_controller(observation):
    return {"vx": 0.0, "vy": 0.0, "vz": 0.0}


SCENARIOS = {
    "peg": {
        "make": PegInHoleScenario,
        "controller": peg_controller,
        "camera": {"cameraDistance": 0.25, "cameraYaw": 45, "cameraPitch": -25, "cameraTargetPosition": [0, 0, 0.04]},
    },
    "trajectory": {
        "make": TrajectoryFollowingScenario,
        "controller": trajectory_controller,
        "camera": {"cameraDistance": 0.6, "cameraYaw": 45, "cameraPitch": -35, "cameraTargetPosition": [0, 0, 0.1]},
    },
}


def _load_controller_from_file(path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("loaded_controller", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "compute_action"):
        raise SystemExit(f"{path} has no compute_action(observation) function")
    return module.compute_action


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="peg")
    parser.add_argument("--controller", choices=["good", "null"], default="good")
    parser.add_argument(
        "--controller-file", type=Path, default=None,
        help="load compute_action(observation) from this file instead of --controller "
             "(e.g. the exact controller.py SimulationPod's GREEN phase synthesized)",
    )
    parser.add_argument("--max-steps", type=int, default=None, help="override the scenario's default step budget")
    args = parser.parse_args()

    config = SCENARIOS[args.scenario]
    scenario = config["make"]()
    if args.controller_file:
        controller = _load_controller_from_file(args.controller_file)
    else:
        controller = null_controller if args.controller == "null" else config["controller"]
    bounds = scenario.default_invariants()
    max_steps = args.max_steps or scenario.default_max_steps()

    client = p.connect(p.GUI)
    p.resetSimulation(physicsClientId=client)
    p.setGravity(0, 0, -9.81, physicsClientId=client)
    p.setTimeStep(TIME_STEP_S, physicsClientId=client)
    p.resetDebugVisualizerCamera(physicsClientId=client, **config["camera"])
    p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0, physicsClientId=client)

    scenario.configure(bounds)
    scenario.build(p, client)

    controller_label = str(args.controller_file) if args.controller_file else args.controller
    print(f"Scenario: {args.scenario}  Controller: {controller_label}  Max steps: {max_steps}")
    print(f"Invariants: {bounds}")
    print("Window open -- watching the run. Press Ctrl+C to stop early.\n")

    has_final_bounds = any(b.scope == "final" for b in bounds)
    outcome = "completed"
    try:
        for step in range(1, max_steps + 1):
            observation = scenario.observe(p, client, step, max_steps)
            metric_values = scenario.metrics(observation)

            if step == 1 or step % 30 == 0:
                readable = " ".join(f"{k}={v:.5f}" for k, v in metric_values.items())
                print(f"  step {step:4d}: {readable}")

            violated = check_instantaneous(metric_values, bounds)
            if violated is not None:
                outcome = f"VIOLATED: {violated.metric} {violated.operator} {violated.threshold} (value={metric_values[violated.metric]:.5f})"
                break
            if has_final_bounds and check_final(metric_values, bounds):
                outcome = f"CONVERGED after {step} steps"
                break

            action = controller(observation)
            scenario.apply_action(p, client, action)
            p.stepSimulation(physicsClientId=client)
            time.sleep(TIME_STEP_S)
        else:
            outcome = f"STALLED: exhausted {max_steps} steps without convergence"
    except KeyboardInterrupt:
        outcome = "interrupted by user"

    print(f"\nOutcome: {outcome}")
    print("Window stays open -- press Ctrl+C to exit.")
    try:
        while True:
            p.stepSimulation(physicsClientId=client)
            time.sleep(TIME_STEP_S)
    except KeyboardInterrupt:
        pass
    finally:
        p.disconnect(client)


if __name__ == "__main__":
    main()
