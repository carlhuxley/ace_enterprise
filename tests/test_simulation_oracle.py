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


class TestTelemetryTraces:
    def test_metric_traces_are_populated_for_every_reported_metric(self):
        oracle = SimulationOracle(PegInHoleScenario(), timeout_s=60)
        telemetry = oracle.run(_ALIGN_AND_INSERT_CONTROLLER, oracle.scenario.default_invariants())

        assert set(telemetry.metric_traces) == {"peak_force", "radial_error", "depth"}
        assert len(telemetry.metric_traces["peak_force"]) > 0
