"""
TrajectoryFollowingScenario — a moving-target tracking task for SimulationPod.

A free-flying actor (a small sphere, gravity disabled) must track a
reference point moving along a fixed circular path. There are no fixtures,
no contact forces, no "seating" -- this exists to prove SimulationOracle and
SimulationPod are genuinely unaware of pegs or holes: swapping this scenario
in for PegInHoleScenario requires no change to either.

Reports two metrics:
  - tracking_error -- distance from the actor to the target, meters (final/convergence)
  - speed          -- actor's linear speed, m/s (instantaneous)
"""
import math

from src.agents.simulation_invariants import MetricBound

ACTOR_RADIUS_M = 0.02
ACTOR_MASS_KG = 0.1
PATH_RADIUS_M = 0.2
ANGULAR_SPEED_RAD_S = 0.5
TIME_STEP_S = 1.0 / 240.0
MAX_SPEED_MPS = 0.3
START_POSITION_M = (0.3, 0.0, 0.1)

_DEFAULT_TRACKING_TOLERANCE_M = 0.02
_DEFAULT_SPEED_LIMIT_MPS = MAX_SPEED_MPS
_DEFAULT_MAX_STEPS = 600


def _clip_vector(vx: float, vy: float, vz: float, limit: float = MAX_SPEED_MPS) -> tuple[float, float, float]:
    """Scale (vx, vy, vz) down to at most `limit` in magnitude, preserving
    direction. Clipping per-axis instead would let a diagonal command exceed
    `limit` in combined speed, which is exactly the metric this scenario bounds."""
    magnitude = math.sqrt(vx * vx + vy * vy + vz * vz)
    if magnitude <= limit or magnitude == 0.0:
        return vx, vy, vz
    scale = limit / magnitude
    return vx * scale, vy * scale, vz * scale


class TrajectoryFollowingScenario:
    def __init__(self) -> None:
        self._actor_id: int | None = None

    def configure(self, invariants: list[MetricBound]) -> None:
        pass  # nothing physical to size from spec'd thresholds

    def build(self, p, client) -> None:
        p.setGravity(0, 0, 0, physicsClientId=client)
        shape = p.createCollisionShape(p.GEOM_SPHERE, radius=ACTOR_RADIUS_M, physicsClientId=client)
        self._actor_id = p.createMultiBody(
            baseMass=ACTOR_MASS_KG,
            baseCollisionShapeIndex=shape,
            basePosition=list(START_POSITION_M),
            physicsClientId=client,
        )

    def _target_position(self, step: int) -> tuple[float, float, float]:
        t = step * TIME_STEP_S
        return (
            PATH_RADIUS_M * math.cos(ANGULAR_SPEED_RAD_S * t),
            PATH_RADIUS_M * math.sin(ANGULAR_SPEED_RAD_S * t),
            START_POSITION_M[2],
        )

    def observe(self, p, client, step, max_steps) -> dict:
        pos, _ = p.getBasePositionAndOrientation(self._actor_id, physicsClientId=client)
        vel, _ = p.getBaseVelocity(self._actor_id, physicsClientId=client)
        tx, ty, tz = self._target_position(step)
        return {
            "step": step, "max_steps": max_steps,
            "x": pos[0], "y": pos[1], "z": pos[2],
            "vx": vel[0], "vy": vel[1], "vz": vel[2],
            "target_x": tx, "target_y": ty, "target_z": tz,
        }

    def metrics(self, observation: dict) -> dict:
        dx = observation["x"] - observation["target_x"]
        dy = observation["y"] - observation["target_y"]
        dz = observation["z"] - observation["target_z"]
        tracking_error = math.sqrt(dx * dx + dy * dy + dz * dz)
        speed = math.hypot(observation["vx"], observation["vy"], observation["vz"])
        return {"tracking_error": tracking_error, "speed": speed}

    def apply_action(self, p, client, action: dict) -> None:
        vx, vy, vz = _clip_vector(float(action["vx"]), float(action["vy"]), float(action["vz"]))
        p.resetBaseVelocity(
            self._actor_id, linearVelocity=[vx, vy, vz], angularVelocity=[0, 0, 0], physicsClientId=client,
        )

    def null_action_source(self) -> str:
        return (
            "def compute_action(observation):\n"
            "    return {'vx': 0.0, 'vy': 0.0, 'vz': 0.0}\n"
        )

    def default_invariants(self) -> list[MetricBound]:
        return [
            MetricBound("speed", "<=", _DEFAULT_SPEED_LIMIT_MPS, "instantaneous"),
            MetricBound(
                "tracking_error", "<=", _DEFAULT_TRACKING_TOLERANCE_M, "final",
                within_steps=_DEFAULT_MAX_STEPS,
            ),
        ]

    def default_max_steps(self) -> int:
        return _DEFAULT_MAX_STEPS

    def controller_contract(self) -> str:
        return """\
Write a Python module defining exactly one function:

    def compute_action(observation: dict) -> dict:
        ...

`observation` has keys: step, max_steps, x, y, z (actor position, meters),
vx, vy, vz (actor velocity, m/s), target_x, target_y, target_z (the moving
target's current position, meters).

Return a dict with keys "vx", "vy", "vz" -- a linear velocity command in m/s
that drives the actor toward (target_x, target_y, target_z). The target
moves continuously, so the controller must track it, not just reach one
fixed point. Velocities are clipped to +/-0.3 m/s. Output only valid Python
code, no explanation.
"""
