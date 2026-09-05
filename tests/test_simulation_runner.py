"""Tests for the generic (scenario-agnostic) simulation loop in
simulation_runner.py. run_simulation() takes plain Python objects for `p`
and `scenario`, so these tests exercise the real bound-checking logic
without needing pybullet installed -- see tests/test_simulation_oracle.py
for real-physics coverage.
"""
from src.agents.simulation_invariants import MetricBound
from src.agents.simulation_runner import (
    check_final,
    check_instantaneous,
    check_integral,
    compare,
    infer_max_steps,
    run_simulation,
)


class TestCompare:
    def test_le(self):
        assert compare(1.0, "<=", 1.0) is True
        assert compare(1.1, "<=", 1.0) is False

    def test_lt(self):
        assert compare(0.9, "<", 1.0) is True
        assert compare(1.0, "<", 1.0) is False

    def test_ge(self):
        assert compare(1.0, ">=", 1.0) is True
        assert compare(0.9, ">=", 1.0) is False

    def test_gt(self):
        assert compare(1.1, ">", 1.0) is True

    def test_eq(self):
        assert compare(1.0, "==", 1.0) is True


class TestInferMaxSteps:
    def test_falls_back_to_scenario_default_with_no_final_bounds(self):
        bounds = [MetricBound("force", "<=", 12.0, "instantaneous")]
        assert infer_max_steps(bounds, scenario_default=500) == 500

    def test_uses_the_largest_within_steps(self):
        bounds = [
            MetricBound("a", "<=", 1.0, "final", within_steps=200),
            MetricBound("b", "<=", 1.0, "final", within_steps=800),
        ]
        assert infer_max_steps(bounds, scenario_default=500) == 800


class TestCheckInstantaneous:
    def test_returns_none_when_satisfied(self):
        bounds = [MetricBound("force", "<=", 12.0, "instantaneous")]
        assert check_instantaneous({"force": 5.0}, bounds) is None

    def test_returns_the_violated_bound(self):
        bounds = [MetricBound("force", "<=", 12.0, "instantaneous")]
        violated = check_instantaneous({"force": 20.0}, bounds)
        assert violated.metric == "force"

    def test_ignores_final_scope_bounds(self):
        bounds = [MetricBound("depth", "<=", 0.02, "final", within_steps=500)]
        assert check_instantaneous({"depth": 5.0}, bounds) is None

    def test_ignores_metrics_the_scenario_did_not_report(self):
        bounds = [MetricBound("torque", "<=", 1.0, "instantaneous")]
        assert check_instantaneous({"force": 999.0}, bounds) is None


class TestCheckFinal:
    def test_false_with_no_final_bounds(self):
        assert check_final({"depth": 0.0}, []) is False

    def test_true_when_all_final_bounds_satisfied(self):
        bounds = [
            MetricBound("radial_error", "<=", 0.0015, "final", within_steps=500),
            MetricBound("depth", "<=", 0.024, "final", within_steps=500),
        ]
        assert check_final({"radial_error": 0.0001, "depth": 0.0}, bounds) is True

    def test_false_when_any_final_bound_unsatisfied(self):
        bounds = [
            MetricBound("radial_error", "<=", 0.0015, "final", within_steps=500),
            MetricBound("depth", "<=", 0.024, "final", within_steps=500),
        ]
        assert check_final({"radial_error": 0.01, "depth": 0.0}, bounds) is False


class TestCheckIntegral:
    def test_returns_violated_bound(self):
        bounds = [MetricBound("energy", "<=", 10.0, "integral")]
        violated = check_integral({"energy": 15.0}, bounds)
        assert violated.metric == "energy"

    def test_none_when_satisfied(self):
        bounds = [MetricBound("energy", "<=", 10.0, "integral")]
        assert check_integral({"energy": 5.0}, bounds) is None


# ---------------------------------------------------------------------------
# run_simulation with a fake scenario/controller/pybullet stub
# ---------------------------------------------------------------------------

class FakePyBullet:
    """Stands in for the `p` module -- run_simulation only calls stepSimulation."""

    def stepSimulation(self, physicsClientId=None):
        pass


class ConvergingScenario:
    """A trivial scenario whose "error" metric decays geometrically toward
    zero and whose "force" metric is always safely bounded."""

    def __init__(self, start_error=1.0, decay=0.5):
        self._error = start_error
        self._decay = decay

    def observe(self, p, client, step, max_steps):
        return {"step": step, "max_steps": max_steps, "error": self._error}

    def metrics(self, observation):
        return {"error": observation["error"], "force": 1.0}

    def apply_action(self, p, client, action):
        self._error *= self._decay


class NullController:
    def compute_action(self, observation):
        return {}


class ConstantErrorScenario(ConvergingScenario):
    """Never converges -- error stays fixed, forcing the step budget to exhaust."""

    def apply_action(self, p, client, action):
        pass


def make_bounds():
    return [
        MetricBound("force", "<=", 12.0, "instantaneous"),
        MetricBound("error", "<=", 0.05, "final", within_steps=50),
    ]


class TestRunSimulationConvergence:
    def test_converges_when_metric_reaches_target(self):
        telemetry = run_simulation(
            FakePyBullet(), 0, ConvergingScenario(), NullController(), make_bounds(),
            max_steps=50, trace_stride=1,
        )
        assert telemetry.success is True
        assert telemetry.phase == "converged"
        assert telemetry.violated is False
        assert telemetry.stalled is False

    def test_stalls_when_never_converging(self):
        telemetry = run_simulation(
            FakePyBullet(), 0, ConstantErrorScenario(), NullController(), make_bounds(),
            max_steps=20, trace_stride=1,
        )
        assert telemetry.success is False
        assert telemetry.phase == "stalled"
        assert telemetry.stalled is True
        assert telemetry.steps_taken == 20

    def test_instantaneous_violation_ends_the_run_immediately(self):
        bounds = [MetricBound("force", "<=", 0.5, "instantaneous")]
        telemetry = run_simulation(
            FakePyBullet(), 0, ConvergingScenario(), NullController(), bounds,
            max_steps=50, trace_stride=1,
        )
        assert telemetry.success is False
        assert telemetry.violated is True
        assert telemetry.violated_metric == "force"
        assert telemetry.phase == "violated:force"
        assert telemetry.steps_taken == 1

    def test_no_final_bounds_means_success_is_completing_without_violation(self):
        bounds = [MetricBound("force", "<=", 12.0, "instantaneous")]
        telemetry = run_simulation(
            FakePyBullet(), 0, ConstantErrorScenario(), NullController(), bounds,
            max_steps=10, trace_stride=1,
        )
        assert telemetry.success is True
        assert telemetry.phase == "completed"

    def test_controller_exception_is_wrapped(self):
        class BrokenController:
            def compute_action(self, observation):
                raise ValueError("boom")

        try:
            run_simulation(
                FakePyBullet(), 0, ConvergingScenario(), BrokenController(), make_bounds(),
                max_steps=50, trace_stride=1,
            )
            raised = False
        except RuntimeError as exc:
            raised = "boom" in str(exc)
        assert raised

    def test_metric_traces_and_peaks_are_recorded(self):
        telemetry = run_simulation(
            FakePyBullet(), 0, ConstantErrorScenario(start_error=2.0), NullController(),
            [MetricBound("force", "<=", 12.0, "instantaneous")],
            max_steps=10, trace_stride=2,
        )
        assert telemetry.peak_metrics["error"] == 2.0
        # step 1 (always sampled) plus every 2nd step through 10: 1,2,4,6,8,10
        assert telemetry.metric_traces["error"] == [2.0] * 6
