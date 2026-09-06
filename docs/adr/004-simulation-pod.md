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

### Subprocess isolation by default; Podman available via SimulationPodmanRunner
`SimulationOracle.run()` executes the simulation in a subprocess by default
(`sys.executable -m src.agents.simulation_runner`, not in-process). This
mirrors the ADR 002 "subprocess vs in-process" rationale, but for a stronger
reason here: PyBullet's `p.DIRECT` client is a stateful, process-global C
extension, so subprocess-per-run guarantees no state leaks between
RED/GREEN/REFACTOR calls, and bounds a crash or runaway controller loop to a
child process with a timeout.

On its own this is a narrower isolation boundary than PythonLanguagePod/
GoLanguagePod get from `PodmanOrchestrator` (network isolation, read-only
workspace, capability drops) -- it's the same milestone GoLanguagePod
started at before ace_enterprise-jww added container sandboxing.
`ImportFilter` runs against generated controller code before it ever
reaches the subprocess, narrowing the blast radius the same way it does for
PythonLanguagePod. Full parity is now available, opt-in, via
`SimulationOracle(scenario, runner=SimulationPodmanRunner())` -- see
"Container sandboxing: SimulationPodmanRunner" below for why it needed a
new runner rather than reusing `PodmanOrchestrator` directly. The bare
subprocess stays the default so no existing caller or test needs podman.

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

### Playbook bullet injection was missing entirely
An early round of live validation (see below) tried to fix real failures by
hand-editing physics hints directly into `TactilePegInHoleScenario.controller_contract()`
-- e.g. telling the LLM the exact velocity-vs-friction threshold that had
caused a stall. That is Reflector's and Curator's job, done manually and
baked permanently into the task spec instead of learned; any resulting
"success" would prove a human can prompt-engineer a fix, not that ACE
learns one. Those hints were reverted.

The deeper problem the exercise surfaced: `SimulationPod._green_prompt()`
had no mechanism to retrieve playbook bullets at all, unlike
`GoLanguagePod._get_go_bullets()`. Even a hypothetical successful
Reflector/Curator pass would have had nowhere to feed its insight back into
synthesis. `SimulationPod` now takes an optional `playbook_manager` and
injects bullets from Curator's four standard sections
(`strategies_and_hard_rules`, `domain_knowledge`, `troubleshooting`,
`code_snippets` -- see Curator's own "Available Sections" prompt; there is no
simulation-specific section to target) into both `_green_prompt()` and
`_refactor_prompt()` as "Learned guidance from previous cycles:".

### Real validation: autonomous multi-cycle learning, confirmed live
With hand-authored hints removed and bullet injection wired, a clean-room
run against `TactilePegInHoleScenario` via `ClaudeCliClient` (Sonnet, no
mocking, no hints) produced two full learning cycles:

- **Attempt 1** (empty playbook): stalled. The archived code's own spiral
  radius grew too slowly to sweep its full search extent within the step
  budget.
- **Reflector**, given only the telemetry summary and the actual failed code
  (recovered from the attempt archive -- a failing attempt is never
  committed to `implementation_file`), correctly diagnosed: *"the search
  pattern's maximum extent must exceed the worst-case uncertainty, and its
  coverage rate must complete that extent well within the budget... never
  impose an artificial constraint tighter than the quantity the controller
  is supposed to discover."* **Curator** wrote 8 bullets from that analysis.
- **Attempt 2** (8 bullets injected, confirmed present in the actual prompt
  sent): fixed exactly that bug, but stalled on an *unrelated* one the first
  bullets didn't cover -- a hardcoded tangential search speed below the
  static-friction threshold needed to move a loaded peg at all (measured
  empirically at roughly 0.02-0.03 m/s for this scenario's mass/geometry).
  Both this and Attempt 1's bug are a genuine, non-obvious robotics gotcha --
  a hand-derived reference controller fell into the same trap on its own
  first pass during this scenario's tuning.
- **Reflector cycle 2**, on Attempt 2's real failure, correctly generalized
  the pattern (*"corrective behavior must have an unconditional execution
  path... never gated behind a single hardcoded threshold"*) -- though it
  also partially over-generalized, treating `z_position` as a forbidden
  sensor reading because the Gherkin says "no position sensor," when the
  contract explicitly provides `z_position` as a legitimate depth reading.
  A real instance of Reflector being partially wrong, left as-is rather than
  corrected by hand. **Curator** wrote 5 more bullets (13 total, two
  independently-discovered failure modes).
- **Attempt 3** (13 bullets): **converged autonomously** in 229 steps --
  `radial_error` final 0.000496m against a 0.0005m tolerance (a 4-micron
  margin), `peak_force` 0.09N, `depth` 0.018m, all within bounds. REFACTOR
  then ran and also passed, further refining the converged controller.

At the time of this run, `TDDCycleRunner._learn()` only ran after a passing
GREEN, so Attempts 1 and 2's learning passes were invoked directly in the
validation script, using the exact same `Reflector.reflect()` /
`Curator.curate()` / `Curator.apply_updates()` call shape `_learn()` uses
internally, just triggered on failure -- a script-level pattern, not yet a
change to the shared harness gate. That gate was promoted into
`TDDCycleRunner` itself in the very next round (see "Stagnation-driven
learning is now native to TDDCycleRunner" below); a fresh run today would
trigger this same learning automatically, no validation-script workaround
needed.

### Infra: a timeout's error message can compound across retries
`ClaudeCliClient` wraps a timed-out subprocess call in a `RuntimeError`
whose message embeds the *entire command it ran* -- including, on a GREEN
retry, the previous attempt's whole prompt. Passed through
`PhaseResult.error` verbatim, that becomes the *next* attempt's
`error_output`, which embeds the whole thing again: an exponentially
growing prompt that makes further timeouts more likely, not less (observed
live: a fully "successful" cascade of this kind burned all 3 of one GREEN
retry budget on nothing but timeouts). `SimulationPod._sanitize_error()`
caps any generic exception's contribution to `PhaseResult.error` at 300
characters, keeping only the tail (where the actionable part of a
`ClaudeCliClient` message -- "...timed out after Ns" -- actually is).

Separately: the `claude` CLI itself has no server-side timeout --
`ClaudeCliClient`'s `timeout` is purely a client-side `subprocess.run()`
deadline. A live retry at `--effort max` (added to `ClaudeCliClient` as an
optional, non-physics-specific parameter -- it's a legitimate lever for
"would more deliberation avoid missing a boundary condition," tested here at
zero cost since it stays within the same subscription/CLI, not a different
model or provider) took over 600 seconds twice without ever returning, while
every attempt that actually completed that session did so under 300s at
default effort. Higher effort trades latency for deliberation; for a
task already constrained by a client-side timeout, that trade was net
negative here -- reverting to default effort with a longer timeout (500s)
is what actually produced Attempt 3's convergence above.

### Stagnation-driven learning is now native to TDDCycleRunner
The three items below (all originally listed as deliberately deferred, or
tracked follow-up) were implemented in the next work session, closing out
this ADR's open items.

`TDDCycleRunner._learn()` was already outcome-agnostic internally --
`EnvironmentFeedback.result` was always `"SUCCESS" if result.success else
"FAILED"`, computed unconditionally. The only thing gating learning to
successful cycles was the *caller's* check, `if cycle_result.green_result.passed:
learn(...)`, immediately before the function returned. `_is_stagnant(green_attempts,
max_green_attempts, green_result)` -- true when every configured GREEN retry
was spent without ever passing or hitting a hard abort -- now gates a second
call to `_learn()` in the early-return failure branch. This is pod-agnostic:
it only needs the attempt count `TDDCycleRunner` already tracks for every
pod, not any pod-specific telemetry format, so Python/Go/TypeScript pods get
the same capability with no changes on their side. A single off-target first
try that a normal retry could still fix is not stagnation (the loop only
reaches this branch after either an abort or the full retry budget is
spent, so "not aborted" already implies "exhausted" by construction) and so
does not spend a Reflector/Curator call on it.

### Windowed bounds formalize stall detection in the Gherkin contract
`MetricBound` gained `scope="windowed"`: `|m_t - m_{t-within_steps}|` must
satisfy `(operator, threshold)` once `within_steps` samples of raw
(unsampled, not `trace_stride`-decimated) history exist for that metric --
checked live, every step, ending the run immediately on violation exactly
like an instantaneous bound. `extract_invariants()` parses "`<metric>` must
change by at least `<value>` every `<N>` steps" into a windowed bound with
operator `">="` (the "must make real progress" stall-detection case this
was built for), but `compare()` is generic over the operator, so a
`<=`-windowed bound ("must not change by more than X in N steps," a
smoothness constraint) works from the same mechanism with no extra code --
just not reachable from this one Gherkin phrasing yet.

Confirmed live: adding a windowed bound to `TactilePegInHoleScenario`'s
invariants catches the null controller's stall at step 989, instead of
running out the full 4000-step budget to report "stalled" only at the very
end -- the same category of stagnation `summarize_telemetry()`'s
"unchanged for the tail of the run" note already *diagnosed* after the
fact is now something a spec can *enforce* during the run itself.

### Container sandboxing: SimulationPodmanRunner
`SimulationOracle` gained an optional `runner` parameter (a
`SimulationPodmanRunner`, `src/agents/simulation_podman_runner.py`); passing
one switches `run()` from the bare host subprocess to the same
rootless-Podman sandbox (`--network none`, `--cap-drop all`, read-only
workspace, tmpfs `/tmp`) every other pod's generated code already runs
in -- confirmed to produce identical telemetry to the bare-subprocess path
for the same controller/scenario. The bare subprocess stays the default
(no podman or image required), so every existing test is unaffected.

Two real mismatches with the existing `PodmanOrchestrator`/`PodmanRunner`
machinery had to be worked around rather than reused directly:

- **Pass/fail isn't the exit code.** Every other pod's oracle (pytest, `go
  test`, vitest) treats `exit_code == 0` as "passed" --
  `PodmanOrchestrator._to_phase_result()` hardcodes exactly that mapping.
  `simulation_runner.py` exits 0 whenever it ran to completion *regardless*
  of whether the simulation converged or stalled -- pass/fail is a nested
  field (`SimulationTelemetry.success`) inside its JSON stdout, a
  fundamentally different contract. `SimulationPodmanRunner` therefore
  doesn't return control to `PodmanOrchestrator.pulse()` at all; `run_simulation_pulse()`
  is a new method or `SimulationOracle` calls directly, returning the raw
  `PulseResult` for `SimulationOracle` to interpret with its own (already
  correct) `_parse_telemetry()`/exit-code logic -- the same one the bare
  subprocess path already used.
- **The scenario/invariants payload isn't a file.** Every other pod's
  `send_pulse(files: dict[str, str])` sends everything the tool needs as
  workspace files. `simulation_runner.py` takes its args as a JSON payload
  on stdin (scenario dotted path, invariants, step budget) -- exactly what
  the bare-subprocess path already piped in. `run_simulation_pulse()`
  writes only the untrusted controller script to the bind-mounted
  workspace and pipes the JSON payload over `podman exec -i`'s stdin,
  unchanged from the bare-subprocess protocol; only the transport (host
  subprocess vs. containerized one) differs.

`docker/harness/Containerfile.simulation` bakes ACE's own trusted oracle
code (`simulation_runner.py` and its direct dependencies -- not the
untrusted controller, which still arrives per-pulse) into the image at
build time, the same trust boundary every other harness image already
draws. pybullet has no prebuilt wheel for the `python:3.12-slim` base, so
the image needs a compiler to build it from source at image-build time
only -- `build-essential` is installed and then purged in the same layer,
so the final image (like every other execution sandbox here) has no
compiler available to code it runs. bandit still scans the controller
script inside the container for the same defense-in-depth reason every
other pod's container runs it, even though `ImportFilter` already screened
the code on the host; a `bandit_high` finding is surfaced as a
`SimulationEnvironmentError` whose message starts with the literal
`"Security gate:"` prefix `_is_abort()` checks for -- `SimulationPod`'s
`_environment_error_message()` helper is what keeps this prefix from being
buried under the ordinary `"SimulationEnvironment: "` wrap every other
environment failure gets, which would otherwise silently defeat abort
detection and waste retries on a finding that will never pass.

### `run_refactor` re-verifies through the oracle
Unlike GoLanguagePod's `gofmt` (semantics-preserving by construction), an LLM
asked to refactor a controller script for clarity/smoothness is not
guaranteed to preserve behavior. `run_refactor` re-runs the full oracle and
only commits the refactored controller if it still passes -- same
never-clobber-a-working-implementation rule as every other pod's refactor
phase.

## Consequences

- `TDDCycleRunner`, `Reflector`, `Curator`, and `Playbook` require zero
  changes to drive a physics simulation instead of a test runner, for any
  shipped scenario -- this is the proof of domain-agnosticism the ADR set
  out to establish, confirmed live end-to-end: a real, un-hinted LLM
  synthesis attempt against `TactilePegInHoleScenario` converged
  autonomously after two real Reflector/Curator learning cycles (see "Real
  validation" above).
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
- All three items originally tracked as deferred/follow-up from this ADR's
  first version are now done, closing the loop: `TDDCycleRunner` reflects
  on a stagnant GREEN failure natively for every pod, not just SimulationPod
  (see "Stagnation-driven learning is now native to TDDCycleRunner");
  `MetricBound` supports `scope="windowed"` for engine-enforced stall
  detection declared directly in a Gherkin spec; and `SimulationOracle` can
  run inside the same rootless-Podman sandbox every other pod's generated
  code already does, via the optional `SimulationPodmanRunner` (bare
  subprocess remains the default -- no podman/image required unless a
  caller opts in).
- `localhost/ace-sim-harness:latest` (built from
  `docker/harness/Containerfile.simulation` via `build_simulation_image()`,
  repo root as context) must exist for the containerized path or
  `tests/test_simulation_podman_runner.py`'s real-container tests -- same
  precedent as the other three per-language harness images, which have no
  build-on-missing fallback either.
