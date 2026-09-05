"""
TactilePegInHoleScenario — a contact-rich peg-in-hole task with no
ground-truth position feedback for the controller.

PegInHoleScenario (peg_in_hole.py) hands the controller its exact (x, y, z)
position and the hole's exact center every step -- a controller can solve it
open-loop by computing radial error directly, never touching a wall. This
scenario tests the opposite, and much more realistic, regime: the controller
gets a wrist force/torque sensor (f_normal, f_lateral_x, f_lateral_y) and a
single, fixed, WRONG calibration estimate of the hole center
(HOLE_CENTER_BIAS_M) -- never its own lateral position, never the true hole
location, never a corrected estimate. The physical clearance (0.2mm) is
tighter than that calibration error (1.5mm), so any controller that simply
trusts its estimate and descends is physically guaranteed to strike the rim.
Passing requires inferring the true center from contact force feedback alone
-- a tactile search/compliance strategy, not coordinate geometry.

metrics() (used for grading, via SimulationOracle) still computes
radial_error/depth from ground truth -- only controller_view() (what the
controller actually receives) hides it. See SimulationScenario.controller_view.
"""
import math

from src.agents.simulation_invariants import MetricBound

PEG_RADIUS_M = 0.008
PEG_HALF_LENGTH_M = 0.03
PEG_MASS_KG = 0.2
BASE_PLATE_HALF_HEIGHT_M = 0.01
HOLE_DEPTH_M = 0.05
SOCKET_HALF_EXTENT_M = 0.05
MAX_SPEED_MPS = 0.4

# The physical clearance is fixed and deliberately tighter than the
# controller's calibration error below -- contact on the rim is guaranteed
# for any strategy that doesn't correct using tactile feedback. 0.5mm (vs.
# a 1.5mm bias) still forces contact but leaves a real capture basin for a
# tactile search -- 0.2mm made even a hand-tuned reference search
# unreliable within budget (each friction-breaking lateral move already
# covers ~0.1-0.25mm, leaving almost no search resolution to spare).
RADIAL_CLEARANCE_M = 0.0005

# The controller's belief about the hole center is wrong by this much, fixed
# for the whole run (a one-time calibration error, not "noise" that could
# average out). The peg starts centered on this belief, not on the true
# center -- exactly what a robot commanding its end effector to its believed
# target would do.
HOLE_CENTER_BIAS_M = (0.0015, 0.0)

_DEFAULT_FORCE_LIMIT_N = 12.0
_DEFAULT_RADIAL_TOLERANCE_M = RADIAL_CLEARANCE_M
_DEFAULT_DEPTH_M = 0.024
_DEFAULT_MAX_STEPS = 4000


def _clip_vector(vx: float, vy: float, vz: float, limit: float = MAX_SPEED_MPS) -> tuple[float, float, float]:
    magnitude = math.sqrt(vx * vx + vy * vy + vz * vz)
    if magnitude <= limit or magnitude == 0.0:
        return vx, vy, vz
    scale = limit / magnitude
    return vx * scale, vy * scale, vz * scale


class TactilePegInHoleScenario:
    def __init__(self) -> None:
        self._hole_floor_z = 2 * BASE_PLATE_HALF_HEIGHT_M
        self._hole_opening_z = self._hole_floor_z + HOLE_DEPTH_M
        self._peg_id: int | None = None

    def configure(self, invariants: list[MetricBound]) -> None:
        pass  # clearance/bias are fixed by design -- see module docstring

    def build(self, p, client) -> None:
        hole_half_gap = PEG_RADIUS_M + RADIAL_CLEARANCE_M

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
        # The peg starts centered on the controller's own (biased) belief
        # about the hole -- a robot commands its end effector to where it
        # thinks the target is, not to the true target it can't see.
        start_x, start_y = HOLE_CENTER_BIAS_M
        start_z = self._hole_opening_z + PEG_HALF_LENGTH_M + 0.01
        self._peg_id = p.createMultiBody(
            baseMass=PEG_MASS_KG,
            baseCollisionShapeIndex=peg_shape,
            basePosition=[start_x, start_y, start_z],
            physicsClientId=client,
        )
        # High friction is load-bearing, not cosmetic: at pybullet's default
        # friction, a resting/loaded peg drifts laterally under gravity alone
        # from residual per-step contact impulses (see resetBaseVelocity's
        # every-step reset in apply_action). With RADIAL_CLEARANCE_M this
        # tight, that passive drift is large enough either to self-center by
        # accident (the null controller "solving" the task with zero control)
        # or to slide off in the wrong direction -- neither is a real test of
        # tactile control. High friction pins a loaded peg in place; a real
        # controller must retreat clear of contact (zero normal load) before
        # it can reposition at all.
        p.changeDynamics(self._peg_id, -1, lateralFriction=2.0, physicsClientId=client)

    def observe(self, p, client, step, max_steps) -> dict:
        pos, _ = p.getBasePositionAndOrientation(self._peg_id, physicsClientId=client)
        vel, _ = p.getBaseVelocity(self._peg_id, physicsClientId=client)
        contacts = p.getContactPoints(bodyA=self._peg_id, physicsClientId=client)

        f_normal = 0.0
        f_lateral_x = 0.0
        f_lateral_y = 0.0
        for c in contacts:
            f_normal += c[9]
            # Net lateral (friction) force resolved into world x/y -- a real
            # wrist F/T sensor's lateral channels, not a position readout.
            lateral1_mag, lateral1_dir, lateral2_mag, lateral2_dir = c[10], c[11], c[12], c[13]
            f_lateral_x += lateral1_mag * lateral1_dir[0] + lateral2_mag * lateral2_dir[0]
            f_lateral_y += lateral1_mag * lateral1_dir[1] + lateral2_mag * lateral2_dir[1]

        px, py, pz = pos
        return {
            "step": step, "max_steps": max_steps,
            # Ground truth -- used by metrics() for grading, hidden from the
            # controller by controller_view() below.
            "x": px, "y": py, "z": pz,
            "vx": vel[0], "vy": vel[1], "vz": vel[2],
            "f_normal": f_normal,
            "f_lateral_x": f_lateral_x,
            "f_lateral_y": f_lateral_y,
            "hole_floor_z": self._hole_floor_z,
            "hole_opening_z": self._hole_opening_z,
        }

    def controller_view(self, observation: dict) -> dict:
        # No x, y, vx, vy, and no true hole position -- only a normal-encoder
        # style depth reading, tactile force/torque, and the controller's
        # fixed (wrong) belief about where the hole is.
        depth_reading = (observation["z"] - PEG_HALF_LENGTH_M) - observation["hole_floor_z"]
        return {
            "step": observation["step"], "max_steps": observation["max_steps"],
            "z_position": depth_reading,
            "f_normal": observation["f_normal"],
            "f_lateral_x": observation["f_lateral_x"],
            "f_lateral_y": observation["f_lateral_y"],
            "hole_x_estimate": HOLE_CENTER_BIAS_M[0],
            "hole_y_estimate": HOLE_CENTER_BIAS_M[1],
        }

    def metrics(self, observation: dict) -> dict:
        # Grades against the TRUE hole center (the world origin) regardless
        # of what the controller believes it is.
        radial_error = math.hypot(observation["x"], observation["y"])
        depth = (observation["z"] - PEG_HALF_LENGTH_M) - observation["hole_floor_z"]
        return {
            "peak_force": observation["f_normal"],
            "radial_error": radial_error,
            "depth": depth,
        }

    def apply_action(self, p, client, action: dict) -> None:
        vx, vy, vz = _clip_vector(float(action["vx"]), float(action["vy"]), float(action["vz"]))
        p.resetBaseVelocity(
            self._peg_id, linearVelocity=[vx, vy, vz], angularVelocity=[0, 0, 0], physicsClientId=client,
        )

    def null_action_source(self) -> str:
        return (
            "def compute_action(observation):\n"
            "    return {'vx': 0.0, 'vy': 0.0, 'vz': 0.0}\n"
        )

    def default_invariants(self) -> list[MetricBound]:
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

`observation` has keys: step, max_steps, z_position (peg height above the
hole floor, meters -- 0 means fully seated), f_normal (current-step normal
contact force, Newtons), f_lateral_x, f_lateral_y (current-step lateral
contact/friction force components, Newtons -- these indicate the direction
and magnitude of any rubbing contact against a wall), hole_x_estimate,
hole_y_estimate (the controller's calibrated belief about the hole center,
meters -- this estimate is fixed for the whole run and MAY BE INACCURATE:
the physical clearance is tighter than typical calibration error, so
descending on this estimate alone risks contact).

There is NO ground-truth (x, y) position or hole location available -- only
force/torque feedback and this one fixed position estimate. A working
controller must use f_normal/f_lateral_x/f_lateral_y to detect and back off
from wall contact (never letting force grow unbounded) and, in the presence
of contact, adjust its horizontal motion to find the true opening (e.g. a
compliant search pattern) rather than assuming hole_x_estimate/hole_y_estimate
is correct.

Return a dict with keys "vx", "vy", "vz" -- a linear velocity command in m/s.
The module may keep state across calls (e.g. module-level variables) to
implement a search pattern over time using `step`. Velocities are clipped to
+/-0.4 m/s, but a large fast command into an obstruction risks a large
impact force -- moving slowly is safer than moving quickly, especially
before you know you're clear of a wall. Output only valid Python code, no
explanation.
"""
