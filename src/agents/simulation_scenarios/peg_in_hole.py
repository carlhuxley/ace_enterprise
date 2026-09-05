"""
PegInHoleScenario — a peg-in-hole insertion task for SimulationPod.

Builds a peg and a square-walled socket entirely from PyBullet primitive
shapes (no URDF assets needed). Reports three metrics a Gherkin spec can
bound:
  - peak_force   -- contact force between peg and socket, Newtons (instantaneous)
  - radial_error -- distance from the peg's centroid to the hole axis, meters
                    (instantaneous)
  - depth        -- remaining gap between the peg's bottom and the hole
                    floor, meters (final/convergence)
"""
import math

from src.agents.simulation_invariants import MetricBound

PEG_RADIUS_M = 0.008
PEG_HALF_LENGTH_M = 0.03
PEG_MASS_KG = 0.05
BASE_PLATE_HALF_HEIGHT_M = 0.01
HOLE_DEPTH_M = 0.05
SOCKET_HALF_EXTENT_M = 0.05
MAX_SPEED_MPS = 0.05

# The peg starts off-axis by more than the default radial tolerance, so a
# controller that never corrects alignment (e.g. SimulationPod's RED-phase
# null controller) genuinely fails to seat rather than trivially succeeding.
INITIAL_OFFSET_M = (0.004, -0.003)

_DEFAULT_FORCE_LIMIT_N = 12.0
_DEFAULT_RADIAL_TOLERANCE_M = 0.0015
_DEFAULT_DEPTH_M = 0.024
_DEFAULT_MAX_STEPS = 500


def _threshold_for(bounds: list[MetricBound], metric: str, default: float) -> float:
    for bound in bounds:
        if bound.metric == metric:
            return bound.threshold
    return default


def _clip_vector(vx: float, vy: float, vz: float, limit: float = MAX_SPEED_MPS) -> tuple[float, float, float]:
    magnitude = math.sqrt(vx * vx + vy * vy + vz * vz)
    if magnitude <= limit or magnitude == 0.0:
        return vx, vy, vz
    scale = limit / magnitude
    return vx * scale, vy * scale, vz * scale


class PegInHoleScenario:
    def __init__(self) -> None:
        self._radial_tolerance_m = _DEFAULT_RADIAL_TOLERANCE_M
        self._hole_floor_z = 2 * BASE_PLATE_HALF_HEIGHT_M
        self._hole_opening_z = self._hole_floor_z + HOLE_DEPTH_M
        self._peg_id: int | None = None

    def configure(self, invariants: list[MetricBound]) -> None:
        # A tighter spec'd radial_error tolerance produces a tighter physical
        # socket clearance, so the fixture always matches what the spec asks for.
        self._radial_tolerance_m = _threshold_for(
            invariants, "radial_error", _DEFAULT_RADIAL_TOLERANCE_M
        )

    def build(self, p, client) -> None:
        hole_half_gap = PEG_RADIUS_M + self._radial_tolerance_m

        base_shape = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=[SOCKET_HALF_EXTENT_M, SOCKET_HALF_EXTENT_M, BASE_PLATE_HALF_HEIGHT_M],
            physicsClientId=client,
        )
        p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=base_shape,
            basePosition=[0, 0, BASE_PLATE_HALF_HEIGHT_M],
            physicsClientId=client,
        )

        wall_half_span = (SOCKET_HALF_EXTENT_M - hole_half_gap) / 2.0
        wall_center_offset = hole_half_gap + wall_half_span
        wall_z = self._hole_floor_z + HOLE_DEPTH_M / 2.0
        for axis, sign in (("x", 1), ("x", -1), ("y", 1), ("y", -1)):
            if axis == "x":
                half_extents = [wall_half_span, SOCKET_HALF_EXTENT_M, HOLE_DEPTH_M / 2.0]
                position = [sign * wall_center_offset, 0, wall_z]
            else:
                half_extents = [SOCKET_HALF_EXTENT_M, wall_half_span, HOLE_DEPTH_M / 2.0]
                position = [0, sign * wall_center_offset, wall_z]
            wall_shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=half_extents, physicsClientId=client)
            p.createMultiBody(
                baseMass=0, baseCollisionShapeIndex=wall_shape, basePosition=position, physicsClientId=client,
            )

        peg_shape = p.createCollisionShape(
            p.GEOM_CYLINDER, radius=PEG_RADIUS_M, height=2 * PEG_HALF_LENGTH_M, physicsClientId=client,
        )
        start_x, start_y = INITIAL_OFFSET_M
        start_z = self._hole_opening_z + PEG_HALF_LENGTH_M + 0.01
        self._peg_id = p.createMultiBody(
            baseMass=PEG_MASS_KG,
            baseCollisionShapeIndex=peg_shape,
            basePosition=[start_x, start_y, start_z],
            physicsClientId=client,
        )

    def observe(self, p, client, step, max_steps) -> dict:
        pos, _ = p.getBasePositionAndOrientation(self._peg_id, physicsClientId=client)
        vel, _ = p.getBaseVelocity(self._peg_id, physicsClientId=client)
        contacts = p.getContactPoints(bodyA=self._peg_id, physicsClientId=client)
        contact_force = sum(c[9] for c in contacts) if contacts else 0.0
        px, py, pz = pos
        return {
            "step": step, "max_steps": max_steps,
            "x": px, "y": py, "z": pz,
            "vx": vel[0], "vy": vel[1], "vz": vel[2],
            "contact_force": contact_force,
            "hole_x": 0.0, "hole_y": 0.0,
            "hole_opening_z": self._hole_opening_z,
            "hole_floor_z": self._hole_floor_z,
        }

    def controller_view(self, observation: dict) -> dict:
        return observation  # nothing hidden -- the controller sees ground truth

    def metrics(self, observation: dict) -> dict:
        radial_error = math.hypot(observation["x"], observation["y"])
        depth = (observation["z"] - PEG_HALF_LENGTH_M) - observation["hole_floor_z"]
        return {
            "peak_force": observation["contact_force"],
            "radial_error": radial_error,
            "depth": depth,
        }

    def apply_action(self, p, client, action: dict) -> None:
        vx, vy, vz = _clip_vector(float(action["vx"]), float(action["vy"]), float(action["vz"]))
        # Angular velocity is zeroed every step: the controller contract is
        # translation-only (no torque command), so without this the peg tips
        # and rolls off the fixture on any off-center wall contact, which has
        # nothing to do with the controller's actual alignment strategy.
        p.resetBaseVelocity(
            self._peg_id, linearVelocity=[vx, vy, vz], angularVelocity=[0, 0, 0], physicsClientId=client,
        )

    def null_action_source(self) -> str:
        return (
            "def compute_action(observation):\n"
            "    return {'vx': 0.0, 'vy': 0.0, 'vz': 0.0}\n"
        )

    def default_invariants(self) -> list[MetricBound]:
        # peak_force is a hard safety limit checked throughout the whole
        # approach (instantaneous). radial_error and depth are the seating
        # accuracy the peg must *converge to*, not maintain from step one --
        # the peg starts off-axis on purpose (INITIAL_OFFSET_M), so treating
        # radial_error as instantaneous would fail every run before the
        # controller gets a chance to align.
        return [
            MetricBound("peak_force", "<=", _DEFAULT_FORCE_LIMIT_N, "instantaneous"),
            MetricBound("radial_error", "<=", _DEFAULT_RADIAL_TOLERANCE_M, "final", within_steps=_DEFAULT_MAX_STEPS),
            MetricBound("depth", "<=", _DEFAULT_DEPTH_M, "final", within_steps=_DEFAULT_MAX_STEPS),
        ]

    def default_max_steps(self) -> int:
        return _DEFAULT_MAX_STEPS

    def controller_contract(self) -> str:
        return """\
Write a Python module defining exactly one function:

    def compute_action(observation: dict) -> dict:
        ...

`observation` has keys: step, max_steps, x, y, z (peg position, meters), vx,
vy, vz (peg velocity, m/s), contact_force (current-step contact force in
Newtons), hole_x, hole_y (hole center, both 0.0), hole_opening_z,
hole_floor_z (both meters).

Return a dict with keys "vx", "vy", "vz" -- a linear velocity command in m/s
for the peg. The peg must reduce its radial distance from (hole_x, hole_y)
to within tolerance before descending, then descend at low speed to seat at
hole_floor_z without exceeding the force limit. Velocities are clipped to
+/-0.05 m/s. Output only valid Python code, no explanation.
"""
