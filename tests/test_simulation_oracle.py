"""Real-physics tests for SimulationOracle (requires the optional `simulation`
dependency group: pip install -e .[simulation]).

Runs against two independent SimulationScenario implementations
(PegInHoleScenario, TrajectoryFollowingScenario) with the exact same
SimulationOracle/simulation_runner code, to prove the oracle is genuinely
scenario-agnostic rather than secretly peg-shaped.

Slower than the mocked SimulationPod tests -- each case spins up a
subprocess running a headless PyBullet simulation for up to a few hundred
steps.
"""
import pytest

from src.agents.simulation_invariants import MetricBound
from src.agents.simulation_oracle import SimulationEnvironmentError, SimulationOracle
from src.agents.simulation_scenarios.peg_in_hole import PegInHoleScenario
from src.agents.simulation_scenarios.peg_in_hole_tactile import TactilePegInHoleScenario
from src.agents.simulation_scenarios.trajectory_following import TrajectoryFollowingScenario

pytest.importorskip("pybullet", reason="pybullet not installed (pip install -e .[simulation])")
pytestmark = pytest.mark.slow

_ALIGN_AND_INSERT_CONTROLLER = (
    "def compute_action(observation):\n"
    "    kp = 2.0\n"
    "    x, y = observation['x'], observation['y']\n"
    "    radial = (x ** 2 + y ** 2) ** 0.5\n"
    "    vz = -0.03 if radial <= 0.001 else -0.005\n"
    "    return {'vx': -kp * x, 'vy': -kp * y, 'vz': vz}\n"
)

_TRACK_TARGET_CONTROLLER = (
    "def compute_action(observation):\n"
    "    kp = 10.0\n"
    "    dx = observation['target_x'] - observation['x']\n"
    "    dy = observation['target_y'] - observation['y']\n"
    "    dz = observation['target_z'] - observation['z']\n"
    "    return {'vx': kp * dx, 'vy': kp * dy, 'vz': kp * dz}\n"
)


class TestPegInHoleScenario:
    @pytest.fixture
    def oracle(self):
        return SimulationOracle(PegInHoleScenario(), timeout_s=60)

    def test_null_controller_stalls_without_seating(self, oracle):
        telemetry = oracle.run(oracle.scenario.null_action_source(), oracle.scenario.default_invariants())

        assert telemetry.success is False
        assert telemetry.stalled is True
        assert telemetry.violated is False

    def test_compliant_controller_seats_within_invariants(self, oracle):
        invariants = oracle.scenario.default_invariants()
        telemetry = oracle.run(_ALIGN_AND_INSERT_CONTROLLER, invariants)

        assert telemetry.success is True
        assert telemetry.phase == "converged"
        for bound in invariants:
            value = telemetry.final_metrics.get(bound.metric)
            assert value is not None

    def test_tighter_tolerance_makes_the_same_controller_fail(self, oracle):
        tight = [
            MetricBound("peak_force", "<=", 12.0, "instantaneous"),
            MetricBound("radial_error", "<=", 1e-9, "final", within_steps=500),
            MetricBound("depth", "<=", 0.024, "final", within_steps=500),
        ]
        telemetry = oracle.run(_ALIGN_AND_INSERT_CONTROLLER, tight)

        assert telemetry.success is False

    def test_missing_compute_action_raises_environment_error(self, oracle):
        with pytest.raises(SimulationEnvironmentError):
            oracle.run("x = 1\n", oracle.scenario.default_invariants())

    def test_controller_exception_raises_environment_error(self, oracle):
        broken = "def compute_action(observation):\n    raise ValueError('boom')\n"
        with pytest.raises(SimulationEnvironmentError):
            oracle.run(broken, oracle.scenario.default_invariants())


class TestTrajectoryFollowingScenario:
    """A completely different physical task -- no fixtures, no contact
    forces, a continuously moving target -- run through the identical
    SimulationOracle used for PegInHoleScenario above."""

    @pytest.fixture
    def oracle(self):
        return SimulationOracle(TrajectoryFollowingScenario(), timeout_s=60)

    def test_null_controller_never_converges(self, oracle):
        telemetry = oracle.run(oracle.scenario.null_action_source(), oracle.scenario.default_invariants())

        assert telemetry.success is False
        assert telemetry.stalled is True

    def test_tracking_controller_converges(self, oracle):
        telemetry = oracle.run(_TRACK_TARGET_CONTROLLER, oracle.scenario.default_invariants())

        assert telemetry.success is True
        assert telemetry.phase == "converged"
        assert telemetry.final_metrics["tracking_error"] <= 0.02

    def test_speed_limit_violation_is_detected(self, oracle):
        # The scenario's own default speed bound equals its actuator's
        # physical clip, so it can never be exceeded by construction (that's
        # the point -- the clip models hardware, not the spec). A tighter
        # spec'd bound than the actuator's own clip is still enforceable.
        strict_speed = [MetricBound("speed", "<=", 0.01, "instantaneous")]
        aggressive = "def compute_action(observation):\n    return {'vx': 100.0, 'vy': 0.0, 'vz': 0.0}\n"
        telemetry = oracle.run(aggressive, strict_speed)

        assert telemetry.success is False
        assert telemetry.violated is True
        assert telemetry.violated_metric == "speed"


_RETREAT_AND_REPOSITION_CONTROLLER = """\
import math
_state = {'phase': 'descend', 'angle': 0.0, 'radius': 0.0003, 'timer': 0}

def compute_action(observation):
    f_normal = observation['f_normal']
    MAX_V = 0.4
    CONTACT = 0.3

    if f_normal > CONTACT:
        _state['phase'] = 'retreat'
        _state['timer'] = 0
        return {'vx': 0.0, 'vy': 0.0, 'vz': MAX_V}

    if _state['phase'] == 'retreat':
        _state['timer'] += 1
        if _state['timer'] < 15:
            return {'vx': 0.0, 'vy': 0.0, 'vz': MAX_V}
        _state['phase'] = 'reposition'
        _state['timer'] = 0
        _state['angle'] += 0.7
        _state['radius'] = min(0.0025, _state['radius'] + 0.0001)

    if _state['phase'] == 'reposition':
        _state['timer'] += 1
        dx = math.cos(_state['angle'])
        dy = math.sin(_state['angle'])
        if _state['timer'] < 6:
            return {'vx': dx * MAX_V * 0.25, 'vy': dy * MAX_V * 0.25, 'vz': 0.0}
        _state['phase'] = 'descend'
        _state['timer'] = 0

    return {'vx': 0.0, 'vy': 0.0, 'vz': -0.05}
"""


class TestTactilePegInHoleScenario:
    """The blinded, contact-rich variant: no ground-truth position, no
    hole-location tracking -- only force/torque feedback and a fixed,
    deliberately-wrong (by more than the physical clearance) hole-center
    estimate. Passing requires tactile search, not coordinate geometry."""

    @pytest.fixture
    def oracle(self):
        return SimulationOracle(TactilePegInHoleScenario(), timeout_s=90)

    def test_null_controller_stalls_without_seating(self, oracle):
        telemetry = oracle.run(oracle.scenario.null_action_source(), oracle.scenario.default_invariants())

        assert telemetry.success is False
        assert telemetry.stalled is True
        assert telemetry.violated is False

    def test_fast_naive_descent_spikes_force_and_violates(self, oracle):
        naive = "def compute_action(observation):\n    return {'vx': 0.0, 'vy': 0.0, 'vz': -0.35}\n"
        telemetry = oracle.run(naive, oracle.scenario.default_invariants())

        assert telemetry.success is False
        assert telemetry.violated is True
        assert telemetry.violated_metric == "peak_force"

    def test_retreat_and_reposition_strategy_converges(self, oracle):
        telemetry = oracle.run(_RETREAT_AND_REPOSITION_CONTROLLER, oracle.scenario.default_invariants())

        assert telemetry.success is True
        assert telemetry.phase == "converged"
        assert telemetry.final_metrics["peak_force"] <= 12.0

    def test_controller_never_receives_ground_truth_position(self, oracle):
        """The controller-facing view must have no x/y/hole-location truth --
        only what a force/torque sensor plus one fixed estimate would give.
        controller_view() runs inside the oracle's subprocess (see
        test_simulation_runner.py's test_controller_only_sees_what_
        controller_view_returns for that generic wiring); here we assert
        directly on this scenario's documented contract."""
        scenario = TactilePegInHoleScenario()
        raw_observation = {
            "step": 1, "max_steps": 10,
            "x": 0.001, "y": 0.002, "z": 0.05,
            "vx": 0.1, "vy": 0.2, "vz": -0.1,
            "f_normal": 1.0, "f_lateral_x": 0.1, "f_lateral_y": -0.1,
            "hole_floor_z": 0.02, "hole_opening_z": 0.07,
        }
        view = scenario.controller_view(raw_observation)

        assert set(view) == {
            "step", "max_steps", "z_position", "f_normal",
            "f_lateral_x", "f_lateral_y", "hole_x_estimate", "hole_y_estimate",
        }
        assert "x" not in view and "y" not in view
        assert "vx" not in view and "vy" not in view

    def test_metrics_still_grade_against_true_hole_center(self):
        """metrics() must use ground truth for grading even though
        controller_view() hides it from the controller."""
        scenario = TactilePegInHoleScenario()
        observation = {
            "x": 0.003, "y": 0.004, "z": 0.05,
            "hole_floor_z": 0.02, "f_normal": 0.0,
        }
        metrics = scenario.metrics(observation)
        assert metrics["radial_error"] == pytest.approx(0.005, abs=1e-9)


class TestTelemetryTraces:
    def test_metric_traces_are_populated_for_every_reported_metric(self):
        oracle = SimulationOracle(PegInHoleScenario(), timeout_s=60)
        telemetry = oracle.run(_ALIGN_AND_INSERT_CONTROLLER, oracle.scenario.default_invariants())

        assert set(telemetry.metric_traces) == {"peak_force", "radial_error", "depth"}
        assert len(telemetry.metric_traces["peak_force"]) > 0
