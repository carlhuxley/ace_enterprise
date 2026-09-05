# ADR 004 — SimulationPod: a generic cyber-physical execution oracle

**Status:** Accepted
**Date:** 2026-09-05

## Context

`LanguagePod` (ADR 002) was designed around CLI test runners: pytest, `go test`,
vitest. Every existing pod treats "passing" as "the toolchain's exit code says
so". We wanted to test a stronger claim: that `TDDCycleRunner` itself has no
hidden dependency on that shape of oracle -- that RED/GREEN/REFACTOR and the
Reflector/Curator/Playbook learning loop are genuinely domain-agnostic.

`SimulationPod` proves this by replacing the test runner with a headless
PyBullet physics simulation. There is no pytest file anywhere in this pod's
execution path -- and, per an explicit design requirement, no single physical
task hardcoded into it either. `SimulationPod` must evaluate *any* physical
scenario (peg insertion, fruit-picking grip force, trajectory following,
deburring, ...), not just the peg-in-hole task it started as a proof of
concept.

## Decision

Implement `SimulationPod` (`src/agents/simulation_pod.py`) as a `LanguagePod`,
parameterized by a `SimulationScenario`. It still exposes exactly `run_red`,
`run_green`, `run_refactor`, `token_usage()` and communicates with
`TDDCycleRunner` exclusively through `PodSpec`/`PhaseResult`/`TokenUsage` --
no changes to the harness were needed.

Four supporting modules do the domain-specific work, layered so that only the
bottom one ever touches pybullet or any one physical task:

- `src/agents/simulation_invariants.py` -- `MetricBound`, a generic
  acceptance criterion (`metric: str`, `operator`, `threshold`, `scope`).
  `extract_invariants()` parses Gherkin clauses into `MetricBound`s
  deterministically via regex (no LLM involved), the same way GoLanguagePod's
  gofmt/go-vet phase runs without one. Neither this module nor anything above
  it knows what "radial_error" or "grip_force" mean physically.
- `src/agents/simulation_scenario.py` -- the `SimulationScenario` protocol
  (`configure`, `build`, `observe`, `metrics`, `apply_action`,
  `null_action_source`, `default_invariants`, `default_max_steps`,
  `controller_contract`) plus `load_scenario()`/`scenario_path()` for loading
  a scenario by dotted path. This is the entire seam between "generic physics
  oracle" and "one physical task" -- everything physical lives behind it.
- `src/agents/simulation_scenarios/*.py` -- concrete scenarios. Three ship:
  `PegInHoleScenario` (peg insertion into a square-walled socket, full
  ground-truth position given to the controller), `TrajectoryFollowingScenario`
  (a free-flying actor tracking a moving target, sharing no code or metric
  names with the peg scenario), and `TactilePegInHoleScenario` (the same
  physical task as `PegInHoleScenario`, but blinded -- see "Partial
  observability" below). Adding a fourth physical task (fruit-picking grip
  force, deburring path accuracy, ...) requires only a new module here.
- `src/agents/simulation_runner.py` -- the actual step loop, run inside a
  subprocess. Checks a scenario's reported metrics against `MetricBound`s
  every step: `scope="instantaneous"` bounds end the run immediately on
  violation; `scope="final"` bounds are convergence targets checked for
  simultaneous satisfaction (success as soon as all are met); `scope="integral"`
  bounds are checked once at the end against the metric's value accumulated
  over the run. Bound-checking is pure Python over plain dicts
  (`compare`, `check_instantaneous`, `check_final`, `check_integral`,
  `infer_max_steps`), so it's unit-tested without pybullet at all
  (`tests/test_simulation_runner.py`) using a fake scenario/controller.

`src/agents/simulation_oracle.py`'s `SimulationOracle` is the thin piece
`SimulationPod` actually calls: it holds a `SimulationScenario` instance only
to read its metadata and dotted path, serializes `MetricBound`s to JSON, and
runs `simulation_runner.py` as `python -m src.agents.simulation_runner` in a
subprocess (`cwd` = repo root, so the dotted scenario import resolves).

## Key choices and rationale

### What "the implementation" means here
For Python/Go/TypeScript pods, GREEN's implementation is the code under test.
Here, GREEN's implementation (`spec.implementation_file`) is a controller
script exposing one function, `compute_action(observation) -> dict`, whose
shape is scenario-defined (`controller_contract()`) and returns an action
dict the scenario itself interprets (`apply_action()`). The physics engine
plays the role pytest plays elsewhere: it is the thing that decides
pass/fail, not an assertion the LLM wrote, and `SimulationPod` never
inspects the action dict's keys itself.

### RED without an LLM-authored test
Other pods' RED phase asks an LLM to write a failing test. SimulationPod's
"test" is the extracted (or scenario-default) `MetricBound` list, which it
writes to `spec.test_file` as JSON, then proves fails against the scenario's
own `null_action_source()` (its "hold still" controller). This is
deterministic and gives a real RED result without any LLM call -- `run_red`
records zero tokens.

### Bound scope is what makes this genuinely generic
The original single-scenario design checked every threshold the same way
(continuously, from step one), which broke as soon as a metric needed to
*converge* rather than *stay bounded* -- e.g. `PegInHoleScenario`'s peg starts
off-axis on purpose, so an instantaneous `radial_error` bound would fail
every run before the controller had a chance to align. Splitting bounds into
`instantaneous` (hard safety limits, checked every step), `final`
(convergence targets, checked for simultaneous satisfaction), and `integral`
(accumulated-over-the-run limits) is what lets one engine host both a
peg-seating task and a continuous-tracking task without either scenario
special-casing the other's semantics.

### Subprocess isolation, not Podman (yet)
`SimulationOracle.run()` executes the simulation in a subprocess via
`sys.executable -m src.agents.simulation_runner`, not in-process. This
mirrors the ADR 002 "subprocess vs in-process" rationale, but for a stronger
reason here: PyBullet's `p.DIRECT` client is a stateful, process-global C
extension, so subprocess-per-run guarantees no state leaks between
RED/GREEN/REFACTOR calls, and bounds a crash or runaway controller loop to a
child process with a timeout.

This is a narrower isolation boundary than PythonLanguagePod/GoLanguagePod get
from `PodmanOrchestrator` (network isolation, read-only workspace, capability
drops) -- it's the same milestone GoLanguagePod started at before
ace_enterprise-jww added container sandboxing. `ImportFilter` runs against
generated controller code before it ever reaches the subprocess, narrowing
the blast radius the same way it does for PythonLanguagePod, but full
Podman-based sandboxing of the simulation subprocess is tracked as follow-up
work, not done here.

### Controller contract is translation-only, per scenario
Both shipped scenarios' `compute_action` returns a linear velocity command
only -- no torque -- and each scenario explicitly zeroes its actor's angular
velocity every step (`resetBaseVelocity(..., angularVelocity=[0,0,0])`) and
vector-clips (not per-axis-clips) commanded velocity to its own physical
speed limit. Per-axis clipping was tried first and let a diagonal command
exceed the actual speed limit in combined magnitude -- exactly the metric
`TrajectoryFollowingScenario` bounds -- which is why both scenarios clip the
velocity vector's magnitude instead.

### Partial observability: `controller_view()` vs. `metrics()`
`PegInHoleScenario` hands the controller its exact position and the hole's
exact center, which lets an LLM solve it open-loop by computing radial error
directly -- proving synthesis works, but never exercising real tactile
control (confirmed live: Sonnet's first attempt against `PegInHoleScenario`
converged in 99 steps with zero contact force the entire run). To force a
genuinely contact-rich task, `SimulationScenario` gained a fourth method,
`controller_view(observation) -> dict`, sitting between `observe()` and the
controller: `observe()`'s output (ground truth) still goes to `metrics()` for
grading, but `controller_view()` derives a separate, possibly-reduced dict
that's the *only* thing `compute_action()` ever sees. `PegInHoleScenario` and
`TrajectoryFollowingScenario` implement it as the identity function;
`TactilePegInHoleScenario` uses it to expose only `z_position`, `f_normal`,
`f_lateral_x/y` (a wrist force/torque sensor), and a fixed, deliberately-wrong
`hole_x_estimate`/`hole_y_estimate` -- no ground-truth (x, y) at all. This
required no protocol-consumer changes beyond `simulation_runner.py`'s loop
(`controller.compute_action(scenario.controller_view(observation))` instead
of the raw observation) and one identity-method addition per existing
scenario.

Tuning the blinded task's difficulty against rigid-body contact turned out to
be its own lesson: a physical clearance loose enough to give a tactile search
real room to converge (0.5mm, vs. a 1.5mm fixed calibration bias) let the
*null* controller solve the task by accident -- a cylinder's rounded edge
catching a box socket's sharp corner self-centers under gravity alone with
pybullet's default friction, with no control at all. Raising the peg's
`lateralFriction` (2.0) fixed this by pinning a loaded/resting peg in place
regardless of clearance width, forcing an active controller to retreat fully
clear of contact (zero normal load) before it can reposition -- confirmed via
a hand-written "retreat, reposition while airborne, redescend" reference
controller (`tests/test_simulation_oracle.py`'s
`test_retreat_and_reposition_strategy_converges`), which is also the strategy
a real compliant-insertion algorithm would use.

### GREEN-retry feedback: summary, not a raw telemetry dump
`PhaseResult.output` (what `TDDCycleRunner` feeds back as `spec.error_output`
on the next GREEN attempt) originally held the full `SimulationTelemetry` as
JSON -- for a 4000-step run with `metric_traces`, that's several thousand
floats. This was found live to be worse than merely noisy: at `temperature=0`
(`ClaudeCliClient`'s default), reproducing the identical unhelpful diagnosis
verbatim on the same failure meant the *next* full prompt is byte-identical
across attempts too, producing byte-identical code, forever -- and separately,
the resulting multi-KB prompts pushed real `claude --print` calls past a
180s timeout on retries. `simulation_runner.summarize_telemetry()` replaces
the raw dump with a few lines per bound (`metric: final=X, target OP Y
[OK|NOT MET]`), flagging when a trace's tail is flat (`-- unchanged for the
tail of the run (no progress toward this target, not just slow)`) --
generically, from `MetricBound`/`SimulationTelemetry` alone, no scenario
knowledge required. `SimulationPod._with_stagnation_note()` additionally
detects when a cycle's current diagnosis is byte-identical to its immediately
preceding one and appends an explicit "try a materially different approach"
note, which is what actually breaks the temperature-0 repeat-forever loop
once the underlying cause (identical feedback text) is understood.

### Every attempt is archived, not just the winner
`commit_to_disk()` only ever writes `spec.implementation_file` on success (by
design, elsewhere in this file) -- but that means a failing attempt's
generated code was previously unrecoverable for post-hoc debugging.
`SimulationPod._archive_attempt()` now writes every GREEN/REFACTOR attempt's
code (pass or fail, even one `ImportFilter` rejects) to
`<implementation_file's dir>/attempts/`, unconditionally.

### Real validation: what actually happened
Run live against `TactilePegInHoleScenario` via `ClaudeCliClient` (Sonnet, no
mocking): two independent attempts each wrote a legitimately sophisticated
strategy -- force-safety overrides, contact detection, an Archimedean spiral
search -- and each stalled at a *different* fixed offset for the same root
cause: the spiral's commanded speed is proportional to its current radius,
and near the search's low-radius starting point that speed falls below the
static-friction threshold needed to move a loaded peg at all (measured
empirically at roughly 0.02-0.03 m/s for this scenario's mass/geometry). Both
attempts got physically wedged at first contact and never moved again. This
is a genuine, non-obvious robotics gotcha -- the same one a hand-derived
reference controller fell into on a first pass during this scenario's own
tuning -- not a synthesis failure exposed by weak prompting.

### `run_refactor` re-verifies through the oracle
Unlike GoLanguagePod's `gofmt` (semantics-preserving by construction), an LLM
asked to refactor a controller script for clarity/smoothness is not
guaranteed to preserve behavior. `run_refactor` re-runs the full oracle and
only commits the refactored controller if it still passes -- same
never-clobber-a-working-implementation rule as every other pod's refactor
phase.

## Consequences

- `TDDCycleRunner`, `Reflector`, `Curator`, and `Playbook` require zero
  changes to drive a physics simulation instead of a test runner, for either
  shipped scenario -- this is the proof of domain-agnosticism the ADR set
  out to establish.
- Adding a new physical task (fruit-picking, deburring, ...) requires only a
  new `SimulationScenario` module; `SimulationPod`, `SimulationOracle`, and
  `simulation_runner.py` need no changes.
- `pybullet` is an optional dependency (`pip install -e .[simulation]`);
  `tests/test_simulation_oracle.py` skips itself when it isn't installed.
  `tests/test_simulation_pod.py` and `tests/test_simulation_runner.py` fake
  the oracle/scenario and pybullet entirely and need no physics dependency.
- SimulationPod is intentionally not wired into `PodFactory`/
  `PolyglotTDDRunner` -- those are scoped to comparing *language*
  implementations of the same feature, which isn't the axis SimulationPod
  demonstrates. It's driven directly via
  `TDDCycleRunner(pod=SimulationPod(llm_client, project_root, scenario))`.
- Full container sandboxing of the simulation subprocess remains open
  follow-up work (tracked via GitHub issue).
- Deliberately deferred (not implemented here): a formal engine-level
  "no-stall" `MetricBound` scope (windowed progress checking, e.g. "this
  metric must change by at least X within any Y-step window") would let a
  Gherkin spec itself penalize the stall pattern found in real validation,
  rather than relying on stagnation-aware retry feedback to help the LLM
  self-correct across attempts. A real, bigger protocol change; tracked as
  follow-up, not folded into this ADR's scope.
  Also deliberately not implemented: letting `Reflector`/`Curator` run on a
  *failed* GREEN, not just a passing one. `TDDCycleRunner._learn()` is shared
  infrastructure across every pod (Python/Go/TypeScript too) -- changing its
  learning gate is a cross-cutting harness decision affecting all of them,
  not a SimulationPod-scoped change, and deserves its own deliberate
  discussion rather than being folded in here.
