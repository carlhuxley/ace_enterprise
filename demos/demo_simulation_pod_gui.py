"""
Demo: Watch SimulationPod's physics oracle in PyBullet's GUI

SimulationPod (src/agents/simulation_pod.py) always runs headless (p.DIRECT)
so it can execute inside a subprocess -- there is nothing to look at when
TDDCycleRunner drives it. This script runs the exact same
SimulationScenario.build/observe/metrics/apply_action calls
simulation_runner.py uses, but against a real p.GUI window with a
hand-written controller, so you can watch a run happen.

Usage:
    .venv/bin/python demos/demo_simulation_pod_gui.py                    # peg-in-hole, full position feedback
    .venv/bin/python demos/demo_simulation_pod_gui.py --scenario trajectory
    .venv/bin/python demos/demo_simulation_pod_gui.py --scenario tactile # blinded, force/torque only
    .venv/bin/python demos/demo_simulation_pod_gui.py --controller null  # watch it fail
    .venv/bin/python demos/demo_simulation_pod_gui.py --scenario tactile \\
        --controller-file path/to/controller.py                        # watch an LLM-synthesized one
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pybullet as p  # noqa: E402

from src.agents.simulation_replay import (  # noqa: E402
    SCENARIOS,
    TIME_STEP_S,
    load_controller_from_file,
    null_controller,
)
from src.agents.simulation_runner import check_final, check_instantaneous  # noqa: E402


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
        controller = load_controller_from_file(args.controller_file)
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

            action = controller(scenario.controller_view(observation))
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
