"""
simulation_runner — the generic subprocess entrypoint SimulationOracle
invokes to actually step a PyBullet simulation.

Scenario-agnostic by construction: this module knows nothing about pegs,
holes, or trajectories. It loads a SimulationScenario by dotted path (see
src/agents/simulation_scenario.py), loads a controller module by file path,
and runs a generic step loop that checks the scenario's reported metrics
against a list of MetricBound thresholds (src/agents/simulation_invariants.py).

Run as a script (`python -m src.agents.simulation_runner <controller_path>`)
with a JSON payload on stdin: {"scenario_path": str, "invariants": [...],
"max_steps": int, "trace_stride": int}. Writes a SimulationTelemetry-shaped
JSON dict to stdout; any exception exits non-zero with a message on stderr.

The bound-checking helpers (_compare, infer_max_steps, check_instantaneous,
check_final, check_integral) take plain dicts/dataclasses, not pybullet
objects, so they're unit-testable without pybullet installed -- only main()
and run_simulation() need a real PyBullet DIRECT client.
"""
import json
import sys
from dataclasses import asdict, dataclass, field

from src.agents.simulation_invariants import MetricBound

__all__ = [
    "SimulationTelemetry",
    "compare",
    "infer_max_steps",
    "check_instantaneous",
    "check_final",
    "check_integral",
    "run_simulation",
    "summarize_telemetry",
    "main",
]

# A metric's trailing trace samples spanning less than this range are
# considered "unchanged" -- i.e. the controller stopped making progress
# toward that bound rather than merely approaching it slowly.
_STAGNATION_EPSILON = 1e-4


@dataclass
class SimulationTelemetry:
    """Outcome of one scenario run, produced by run_simulation()."""

    success: bool
    steps_taken: int
    violated: bool
    violated_metric: str | None
    stalled: bool
    phase: str
    peak_metrics: dict = field(default_factory=dict)
    final_metrics: dict = field(default_factory=dict)
    metric_traces: dict = field(default_factory=dict)
    failure_reason: str | None = None


def compare(value: float, operator: str, threshold: float) -> bool:
    if operator == "<=":
        return value <= threshold
    if operator == "<":
        return value < threshold
    if operator == ">=":
        return value >= threshold
    if operator == ">":
        return value > threshold
    if operator == "==":
        return value == threshold
    raise ValueError(f"unknown operator: {operator!r}")


def infer_max_steps(bounds: list[MetricBound], scenario_default: int) -> int:
    """Step budget = the largest within_steps declared by any final-scope
    bound, or the scenario's own default if none declare one."""
    within = [b.within_steps for b in bounds if b.scope == "final" and b.within_steps is not None]
    return max(within) if within else scenario_default


def check_instantaneous(metric_values: dict, bounds: list[MetricBound]) -> MetricBound | None:
    """Return the first violated instantaneous bound this step, or None."""
    for bound in bounds:
        if bound.scope != "instantaneous":
            continue
        value = metric_values.get(bound.metric)
        if value is None:
            continue
        if not compare(value, bound.operator, bound.threshold):
            return bound
    return None


def check_final(metric_values: dict, bounds: list[MetricBound]) -> bool:
    """True if every final-scope bound is satisfied by this step's metrics.

    A scenario/spec with no final-scope bounds at all has nothing to
    converge on; success is then decided by completing the run without an
    instantaneous violation (see run_simulation()), not by this function.
    """
    finals = [b for b in bounds if b.scope == "final"]
    if not finals:
        return False
    return all(
        metric_values.get(b.metric) is not None and compare(metric_values[b.metric], b.operator, b.threshold)
        for b in finals
    )


def check_integral(accumulated: dict, bounds: list[MetricBound]) -> MetricBound | None:
    """Return the first violated integral-scope bound, or None."""
    for bound in bounds:
        if bound.scope != "integral":
            continue
        value = accumulated.get(bound.metric)
        if value is None:
            continue
        if not compare(value, bound.operator, bound.threshold):
            return bound
    return None


def summarize_telemetry(telemetry: SimulationTelemetry, bounds: list[MetricBound]) -> str:
    """A concise, scenario-agnostic diagnosis of one run, meant to be fed
    back as GREEN-retry context (PhaseResult.output) -- not a raw telemetry
    dump. A full trace of 1000+ float samples per metric buries the signal a
    retrying LLM actually needs: which bound(s) failed, by how much, and
    whether the metric was still moving toward the target or had simply
    stopped (a stall, not slow progress).
    """
    lines = [f"{'PASSED' if telemetry.success else 'FAILED'} ({telemetry.phase}) after {telemetry.steps_taken} step(s)"]
    for bound in bounds:
        value = telemetry.final_metrics.get(bound.metric)
        if value is None:
            continue
        met = compare(value, bound.operator, bound.threshold)
        status = "OK" if met else "NOT MET"
        note = ""
        if not met:
            trace = telemetry.metric_traces.get(bound.metric) or []
            tail = trace[-max(1, len(trace) // 5):] if trace else []
            if len(tail) >= 3 and (max(tail) - min(tail)) < _STAGNATION_EPSILON:
                note = " -- unchanged for the tail of the run (no progress toward this target, not just slow)"
        lines.append(f"- {bound.metric}: final={value:.6g}, target {bound.operator} {bound.threshold} [{status}]{note}")
    if telemetry.failure_reason:
        lines.append(f"failure_reason: {telemetry.failure_reason}")
    return "\n".join(lines)


def run_simulation(p, client, scenario, controller, bounds: list[MetricBound], max_steps: int, trace_stride: int) -> SimulationTelemetry:
    peak_metrics: dict[str, float] = {}
    accumulated: dict[str, float] = {}
    metric_traces: dict[str, list] = {}
    final_metrics: dict[str, float] = {}
    has_final_bounds = any(b.scope == "final" for b in bounds)

    violated_bound = None
    converged = False
    step = 0

    for step in range(1, max_steps + 1):
        observation = scenario.observe(p, client, step, max_steps)
        metric_values = scenario.metrics(observation)
        final_metrics = metric_values

        for name, value in metric_values.items():
            peak_metrics[name] = max(peak_metrics.get(name, value), value)
            accumulated[name] = accumulated.get(name, 0.0) + value
            if step == 1 or step % trace_stride == 0:
                metric_traces.setdefault(name, []).append(round(value, 6))

        violated_bound = check_instantaneous(metric_values, bounds)
        if violated_bound is not None:
            break

        if has_final_bounds and check_final(metric_values, bounds):
            converged = True
            break

        try:
            controller_observation = scenario.controller_view(observation)
            action = controller.compute_action(controller_observation)
        except Exception as exc:
            raise RuntimeError(f"controller.compute_action failed: {exc}") from exc
        scenario.apply_action(p, client, action)
        p.stepSimulation(physicsClientId=client)

    integral_violation = check_integral(accumulated, bounds)

    violated = violated_bound is not None
    # "Stalled" only applies when there was a convergence target to miss --
    # a scenario/spec with no final-scope bounds has nothing to stall on, and
    # simply completing the run without violation is success (see below).
    stalled = not violated and not converged and has_final_bounds and step >= max_steps
    success = not violated and integral_violation is None and (converged or not has_final_bounds)

    if violated_bound is not None:
        phase = f"violated:{violated_bound.metric}"
        failure_reason = (
            f"{violated_bound.metric} violated {violated_bound.operator} {violated_bound.threshold} "
            f"(value={final_metrics.get(violated_bound.metric)})"
        )
    elif integral_violation is not None:
        phase = f"violated:{integral_violation.metric}"
        failure_reason = (
            f"{integral_violation.metric} (integral) violated {integral_violation.operator} "
            f"{integral_violation.threshold} (accumulated={accumulated.get(integral_violation.metric)})"
        )
    elif converged:
        phase = "converged"
        failure_reason = None
    elif stalled:
        phase = "stalled"
        failure_reason = f"stalled: exhausted {max_steps} steps without convergence"
    else:
        phase = "completed"
        failure_reason = None

    return SimulationTelemetry(
        success=success,
        steps_taken=step,
        violated=violated,
        violated_metric=violated_bound.metric if violated_bound else None,
        stalled=stalled,
        phase=phase,
        peak_metrics={k: round(v, 6) for k, v in peak_metrics.items()},
        final_metrics={k: round(v, 6) for k, v in final_metrics.items()},
        metric_traces=metric_traces,
        failure_reason=failure_reason,
    )


def main() -> None:
    import importlib.util

    from src.agents.simulation_scenario import load_scenario

    payload = json.loads(sys.stdin.read())
    bounds = [MetricBound(**b) for b in payload["invariants"]]
    trace_stride = payload["trace_stride"]

    scenario = load_scenario(payload["scenario_path"])
    scenario.configure(bounds)
    max_steps = min(payload["max_steps"], infer_max_steps(bounds, scenario.default_max_steps()))

    controller_path = sys.argv[1]
    spec = importlib.util.spec_from_file_location("controller", controller_path)
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    if not hasattr(controller, "compute_action"):
        raise RuntimeError("controller module has no compute_action(observation) function")

    import pybullet as p

    client = p.connect(p.DIRECT)
    try:
        p.resetSimulation(physicsClientId=client)
        p.setGravity(0, 0, -9.81, physicsClientId=client)
        p.setTimeStep(1.0 / 240.0, physicsClientId=client)
        scenario.build(p, client)
        telemetry = run_simulation(p, client, scenario, controller, bounds, max_steps, trace_stride)
    finally:
        p.disconnect(client)

    sys.stdout.write(json.dumps(asdict(telemetry)))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- surfaced to parent via stderr/exit code
        print(str(exc), file=sys.stderr)
        sys.exit(1)
