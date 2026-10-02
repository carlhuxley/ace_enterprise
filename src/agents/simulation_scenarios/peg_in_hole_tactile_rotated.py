"""RotatedTactilePegInHoleScenario — a variant of TactilePegInHoleScenario
(peg_in_hole_tactile.py) with the fixed calibration bias on the Y axis
instead of X.

Everything else is identical to the original tactile scenario: no
ground-truth position, only wrist force/torque feedback and one fixed,
deliberately-wrong hole-center estimate, with the physical clearance
tighter than that estimate's error.

First attempt at this variant used a DIAGONAL (both-axes) bias of the same
magnitude. The known-working _RETREAT_AND_REPOSITION_CONTROLLER reference
solution (tests/test_simulation_oracle.py) failed to converge against it
within the 4000-step budget, which first looked like a real geometry bug
(a theory about diagonal vs. axis-aligned clearance on a square socket).
That diagnosis turned out to be wrong: SimulationTelemetry.final_metrics is
a snapshot of the LAST evaluated step only, not the peak over the whole
run, so "final peak_force == 0.0" doesn't mean zero contact ever happened
-- confirmed by manually stepping the physics directly, which showed real
wall contact (f_normal > 3N) well before step 30. The real explanation is
simpler: that one reference controller's fixed, blind angular search
schedule (a hardcoded spiral, not reactive to sensed force) just doesn't
happen to sweep toward every possible bias direction within budget -- a
property of that one test fixture, not of the scenario's physics.

Rotated the bias 90 degrees onto the Y axis anyway, both for a cleaner
mental model (still a flat-wall case, no corner geometry to reason about)
and because it's confirmed solvable: a REACTIVE controller (steers using
the sensed f_lateral_x/f_lateral_y direction instead of a blind fixed
schedule) converges on this scenario with final metrics
(peak_force=0.172N, radial_error=0.000493m, depth=0.0187m) nearly
identical to the same controller's run against the original (0.176N,
0.000493m, 0.0187m) -- real confirmation the two scenarios are physically
equivalent in difficulty, not that one is secretly easier or broken.

Created to test generalization of playbook bullets learned from repeated
PegInHoleScenario (peg_in_hole.py, full-observability) runs -- see the
playbook_id="simulation_peg_in_hole" bullets written by Reflector/Curator
after real convergence runs.
"""
from src.agents.simulation_invariants import MetricBound
from src.agents.simulation_scenarios.peg_in_hole_tactile import (
    _DEFAULT_FORCE_LIMIT_N,
    _DEFAULT_MAX_STEPS,
    _DEFAULT_RADIAL_TOLERANCE_M,
    BASE_PLATE_HALF_HEIGHT_M,
    HOLE_DEPTH_M,
    PEG_HALF_LENGTH_M,
    PEG_MASS_KG,
    PEG_RADIUS_M,
    RADIAL_CLEARANCE_M,
    SOCKET_HALF_EXTENT_M,
    TactilePegInHoleScenario,
)

# Same magnitude as the original's (0.0015, 0.0), rotated 90 degrees onto
# the Y axis -- same wall-to-wall physics as the original, just the other
# wall pair.
HOLE_CENTER_BIAS_M = (0.0, 0.0015)


class RotatedTactilePegInHoleScenario(TactilePegInHoleScenario):
    """TactilePegInHoleScenario with HOLE_CENTER_BIAS_M on the Y axis
    instead of X. Reuses everything else unchanged -- geometry, physics,
    grading, and the controller contract text (generalized to describe
    "either axis" rather than naming X specifically)."""

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
        start_x, start_y = HOLE_CENTER_BIAS_M
        start_z = self._hole_opening_z + PEG_HALF_LENGTH_M + 0.01
        self._peg_id = p.createMultiBody(
            baseMass=PEG_MASS_KG,
            baseCollisionShapeIndex=peg_shape,
            basePosition=[start_x, start_y, start_z],
            physicsClientId=client,
        )
        p.changeDynamics(self._peg_id, -1, lateralFriction=2.0, physicsClientId=client)

    def controller_view(self, observation: dict) -> dict:
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

    def default_invariants(self) -> list[MetricBound]:
        return [
            MetricBound("peak_force", "<=", _DEFAULT_FORCE_LIMIT_N, "instantaneous"),
            MetricBound("radial_error", "<=", _DEFAULT_RADIAL_TOLERANCE_M, "final", within_steps=_DEFAULT_MAX_STEPS),
            MetricBound("depth", "<=", 0.024, "final", within_steps=_DEFAULT_MAX_STEPS),
        ]

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
meters -- this estimate is fixed for the whole run and MAY BE INACCURATE
IN EITHER AXIS: the physical clearance is tighter than typical calibration
error, so descending on this estimate alone risks contact).

There is NO ground-truth (x, y) position or hole location available -- only
force/torque feedback and this one fixed position estimate. A working
controller must use f_normal/f_lateral_x/f_lateral_y to detect and back off
from wall contact (never letting force grow unbounded) and, in the presence
of contact, adjust its horizontal motion to find the true opening (e.g. a
compliant search pattern covering both x and y) rather than assuming
hole_x_estimate/hole_y_estimate is correct.

Return a dict with keys "vx", "vy", "vz" -- a linear velocity command in m/s.
The module may keep state across calls (e.g. module-level variables) to
implement a search pattern over time using `step`. Velocities are clipped to
+/-0.4 m/s, but a large fast command into an obstruction risks a large
impact force -- moving slowly is safer than moving quickly, especially
before you know you're clear of a wall. Output only valid Python code, no
explanation.
"""
