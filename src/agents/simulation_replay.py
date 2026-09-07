"""Replay an archived SimulationPod attempt -- shared by
demos/demo_simulation_pod_gui.py (live p.GUI playback) and `ace view`
(headless telemetry inspection + on-demand video export).

SimulationPod's own execution path (run_green/run_refactor -> SimulationOracle
-> simulation_runner.py's p.DIRECT step loop) is untouched by anything here --
this module only ever replays a controller that's already been archived to
disk by SimulationPod._archive_attempt(), after the fact.
"""

from __future__ import annotations

import importlib.util
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.agents.simulation_invariants import MetricBound
from src.agents.simulation_runner import SimulationTelemetry
from src.agents.simulation_scenarios.peg_in_hole import PegInHoleScenario
from src.agents.simulation_scenarios.peg_in_hole_tactile import TactilePegInHoleScenario
from src.agents.simulation_scenarios.trajectory_following import TrajectoryFollowingScenario

TIME_STEP_S = 1.0 / 240.0
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_FPS = 30

# ER_TINY_RENDERER's default flat/ambient lighting and PyBullet's default
# uncolored gray materials wash the whole scene out to near-uniform light
# gray -- fine for a live debug window, not for a demonstration video. Both
# are cosmetic, applied only here (never in a scenario's build()), so the
# live synthesis path's rendering-free execution is untouched.
_ENVIRONMENT_COLOR = (0.62, 0.60, 0.55, 1.0)  # warm neutral gray -- base/walls/fixtures
_ACTOR_COLOR = (0.20, 0.45, 0.90, 1.0)        # blue -- the controlled body


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


_tactile_state = None


def tactile_controller(observation):
    """The same hand-verified "retreat, reposition while airborne, redescend"
    reference controller used in tests/test_simulation_oracle.py's
    test_retreat_and_reposition_strategy_converges -- avoids fighting static
    friction by only repositioning once fully clear of contact."""
    global _tactile_state
    if _tactile_state is None:
        _tactile_state = {"phase": "descend", "angle": 0.0, "radius": 0.0003, "timer": 0}
    s = _tactile_state
    f_normal = observation["f_normal"]
    max_v = 0.4
    contact = 0.3

    if f_normal > contact:
        s["phase"] = "retreat"
        s["timer"] = 0
        return {"vx": 0.0, "vy": 0.0, "vz": max_v}

    if s["phase"] == "retreat":
        s["timer"] += 1
        if s["timer"] < 15:
            return {"vx": 0.0, "vy": 0.0, "vz": max_v}
        s["phase"] = "reposition"
        s["timer"] = 0
        s["angle"] += 0.7
        s["radius"] = min(0.0025, s["radius"] + 0.0001)

    if s["phase"] == "reposition":
        s["timer"] += 1
        dx, dy = math.cos(s["angle"]), math.sin(s["angle"])
        if s["timer"] < 6:
            return {"vx": dx * max_v * 0.25, "vy": dy * max_v * 0.25, "vz": 0.0}
        s["phase"] = "descend"
        s["timer"] = 0

    return {"vx": 0.0, "vy": 0.0, "vz": -0.05}


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
    "tactile": {
        "make": TactilePegInHoleScenario,
        "controller": tactile_controller,
        "camera": {"cameraDistance": 0.25, "cameraYaw": 45, "cameraPitch": -25, "cameraTargetPosition": [0, 0, 0.04]},
    },
}


def load_controller_from_file(path: Path):
    spec = importlib.util.spec_from_file_location("loaded_controller", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "compute_action"):
        raise SystemExit(f"{path} has no compute_action(observation) function")
    return module.compute_action


@dataclass
class AttemptRecord:
    """Everything needed to replay one archived SimulationPod attempt."""

    controller_path: Path
    controller: Any  # compute_action(observation) -> dict
    scenario_name: str
    telemetry: SimulationTelemetry | None
    invariants: list[MetricBound]


def resolve_attempt(path: Path, *, scenario_override: str | None = None) -> AttemptRecord:
    """Given a path to an archived attempt's `.py` or `.json` file (either
    works -- resolved via stem, matching SimulationPod._archive_attempt's
    convention of writing both under the same base name), load the
    controller and, if present, its persisted telemetry+invariants.

    Attempts archived before telemetry persistence shipped have no `.json`
    sibling -- `telemetry`/`invariants` come back empty rather than raising,
    and `scenario_override` (or a default) is needed for --video since there
    are no persisted invariants to infer a scenario's metric names from.
    """
    base = path.with_suffix("")
    py_path = base.with_suffix(".py")
    json_path = base.with_suffix(".json")
    if not py_path.exists():
        raise FileNotFoundError(f"no archived attempt at {py_path}")

    telemetry: SimulationTelemetry | None = None
    invariants: list[MetricBound] = []
    if json_path.exists():
        payload = json.loads(json_path.read_text())
        telemetry = SimulationTelemetry(**payload["telemetry"])
        invariants = [MetricBound(**b) for b in payload["invariants"]]

    scenario_name = scenario_override or "peg"
    if scenario_name not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario_name!r} (expected one of {sorted(SCENARIOS)})")

    return AttemptRecord(
        controller_path=py_path,
        controller=load_controller_from_file(py_path),
        scenario_name=scenario_name,
        telemetry=telemetry,
        invariants=invariants,
    )


def _colorize_bodies(p, client) -> None:
    """Color the scene for contrast: every scenario (PegInHoleScenario,
    TrajectoryFollowingScenario, TactilePegInHoleScenario) builds its fixed
    environment (base/walls/fixtures) first and its one controlled body
    (peg/actor) last -- so the last body created gets an accent color and
    everything else gets a single neutral one, without needing to know any
    scenario-specific attribute name (stays scenario-agnostic). Purely
    cosmetic (video-rendering only); a scenario's build() is never touched."""
    num_bodies = p.getNumBodies(physicsClientId=client)
    for i in range(num_bodies):
        body_id = p.getBodyUniqueId(i, physicsClientId=client)
        color = _ACTOR_COLOR if i == num_bodies - 1 else _ENVIRONMENT_COLOR
        p.changeVisualShape(body_id, -1, rgbaColor=color, physicsClientId=client)
        for link_index in range(p.getNumJoints(body_id, physicsClientId=client)):
            p.changeVisualShape(body_id, link_index, rgbaColor=color, physicsClientId=client)


def render_attempt_video(
    attempt: AttemptRecord, output_path: Path, max_steps: int | None = None, frame_stride: int = 1,
) -> Path:
    """Headless replay of an archived attempt, capturing one frame per
    physics step via PyBullet's CPU software rasterizer (ER_TINY_RENDERER --
    no GPU or display server needed) and muxing them to `output_path`.

    Mirrors demos/demo_simulation_pod_gui.py's step loop exactly, except:
    p.DIRECT instead of p.GUI (no window), no time.sleep (renders as fast as
    possible, nothing needs to play back live), and a getCameraImage() call
    per step instead of a debug-visualizer window.

    frame_stride > 1 captures every Nth step instead of every step -- the
    physics/controller loop still runs every step (so a stalled run's
    outcome is unaffected), only the expensive getCameraImage() call is
    skipped on the steps in between. A stalled attempt exhausting a
    4000-step budget renders roughly frame_stride times faster, at the cost
    of choppier (effectively accelerated) playback.
    """
    import imageio
    import numpy as np
    import pybullet as p

    from src.agents.simulation_runner import check_final, check_instantaneous

    config = SCENARIOS[attempt.scenario_name]
    scenario = config["make"]()
    bounds = attempt.invariants or scenario.default_invariants()
    steps_budget = max_steps or scenario.default_max_steps()

    client = p.connect(p.DIRECT)
    try:
        p.resetSimulation(physicsClientId=client)
        p.setGravity(0, 0, -9.81, physicsClientId=client)
        p.setTimeStep(TIME_STEP_S, physicsClientId=client)
        scenario.configure(bounds)
        scenario.build(p, client)
        _colorize_bodies(p, client)

        cam = config["camera"]
        view_matrix = p.computeViewMatrixFromYawPitchRoll(
            cameraTargetPosition=cam["cameraTargetPosition"],
            distance=cam["cameraDistance"],
            yaw=cam["cameraYaw"],
            pitch=cam["cameraPitch"],
            roll=0,
            upAxisIndex=2,
        )
        proj_matrix = p.computeProjectionMatrixFOV(
            fov=60, aspect=VIDEO_WIDTH / VIDEO_HEIGHT, nearVal=0.01, farVal=10.0,
        )

        has_final_bounds = any(b.scope == "final" for b in bounds)
        frames = []
        for step in range(1, steps_budget + 1):
            observation = scenario.observe(p, client, step, steps_budget)
            metric_values = scenario.metrics(observation)

            if step == 1 or step % frame_stride == 0:
                _, _, rgba, _, _ = p.getCameraImage(
                    VIDEO_WIDTH, VIDEO_HEIGHT,
                    viewMatrix=view_matrix, projectionMatrix=proj_matrix,
                    renderer=p.ER_TINY_RENDERER, physicsClientId=client,
                    lightDirection=[0.6, -0.8, 1.2],
                    shadow=1,
                    lightAmbientCoeff=0.35,
                    lightDiffuseCoeff=0.75,
                    lightSpecularCoeff=0.2,
                )
                # ER_TINY_RENDERER returns a flat sequence, not a pre-shaped
                # array -- reshape to (H, W, 4) before dropping the alpha channel.
                frame = np.asarray(rgba, dtype=np.uint8).reshape(VIDEO_HEIGHT, VIDEO_WIDTH, 4)
                frames.append(frame[:, :, :3])

            if check_instantaneous(metric_values, bounds) is not None:
                break
            if has_final_bounds and check_final(metric_values, bounds):
                break

            action = attempt.controller(scenario.controller_view(observation))
            scenario.apply_action(p, client, action)
            p.stepSimulation(physicsClientId=client)
    finally:
        p.disconnect(client)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimwrite(output_path, frames, fps=VIDEO_FPS)
    return output_path
