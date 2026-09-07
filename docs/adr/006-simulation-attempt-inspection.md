# ADR 006 — `ace view`: telemetry persistence + on-demand headless video for SimulationPod attempts

**Status:** Accepted
**Date:** 2026-09-07

## Context

After surfacing SimulationPod's autonomous peg-in-hole recovery in the
top-level README (ADR 004's result), the natural next request is "can I
watch it?" Two real gaps stood in the way:

1. **No telemetry survives past the process that produced it.**
   `SimulationPod._archive_attempt()` (`src/agents/simulation_pod.py`)
   already writes every GREEN/REFACTOR attempt's *code* to
   `<impl_dir>/attempts/`, pass or fail, unconditionally — but the raw
   `SimulationTelemetry` a run produces is only ever reduced to a summary
   string for the LLM's next prompt and then discarded. There was no way to
   inspect what actually happened in a past attempt.
2. **No headless way to watch a run.** `demos/demo_simulation_pod_gui.py`
   can replay an archived attempt's controller, but only in a live `p.GUI`
   window — nothing works without a local display (CI, servers, WSL without
   an X server).

A proposal (relayed from an external review) suggested a synced two-pane
video+terminal "split view," gated behind `--gui`/`--record` flags threaded
through the live synthesis path. Rejected: a true synced composite requires
compositing frame timestamps against Reflector/Curator log lines into one
render — real additional work for a demonstration nicety, not a debugging
tool — and threading any recording flag through `SimulationPod` →
`SimulationOracle` → `simulation_runner.py`'s step loop touches the one path
that must stay fast and display-free by design.

## Decision

**Telemetry persistence is unconditional and lives entirely inside
`SimulationPod`.** `_archive_attempt` now returns the attempt's base path
(no extension); `_run_oracle` — the one place that already holds the raw
`telemetry: SimulationTelemetry` and the `invariants` it was checked
against — writes a sibling `{base}.json` (`{"telemetry": ..., "invariants": ...}`)
right after computing it. This is a JSON write next to a write that was
*already* unconditional (the code archive), not a new default-path risk: no
rendering, no display, negligible I/O next to an LLM call and a full physics
rollout. `SimulationOracle`, `simulation_runner.py`'s step loop, and
`TDDCycleRunner` are untouched.

Persisting `invariants` alongside `telemetry` (not telemetry alone) means
`ace view` can call the *exact same* `summarize_telemetry(telemetry, invariants)`
used live during synthesis — one formatting path, not two, so the printed
summary reads identically whether you're watching a build happen or
inspecting it after the fact.

**Video rendering is strictly on-demand replay, never live capture.** A new
`src/agents/simulation_replay.py` module (shared with, and extracted from,
`demos/demo_simulation_pod_gui.py` — `SCENARIOS`, `load_controller_from_file`
moved there rather than duplicated) adds `render_attempt_video()`: it
re-runs an *already-archived* controller through the scenario headlessly
(`p.connect(p.DIRECT)`, not `p.GUI`), capturing one frame per step via
`p.getCameraImage(..., renderer=p.ER_TINY_RENDERER)` — PyBullet's CPU
software rasterizer, so no GPU or display server is needed, confirmed
working under WSL — and muxes them to an `.mp4` via `imageio`/`imageio-ffmpeg`
(new dependency, `imageio-ffmpeg` bundles a static ffmpeg binary so no system
install is required). Because this replays a controller that's already on
disk, it can never affect synthesis speed or isolation — the two are
completely decoupled in time, not just in code path.

**The run-id is just a filesystem path — no new addressing scheme invented.**
`SimulationPod._archive_attempt`'s existing filename convention
(`{stem}_cycle{N}_{phase}_attempt{M}`) already uniquely identifies an
attempt; `ace view <path>` accepts either the `.py` or the `.json` sibling,
resolved via stem. Attempts archived before this shipped have no `.json` —
`ace view` degrades to "no telemetry recorded for this attempt" rather than
erroring, and accepts `--scenario` to still render a video for one of those.

**Explicit non-goal: Reflector/Curator diagnosis text per attempt.** That
lives in `TDDCycleRunner`, the shared harness every pod (Python/Go/TS/
Simulation) uses — persisting it keyed by attempt would be a harness-wide
change, not a SimulationPod-specific one. Confirmed with the user: filed as
a separate follow-up rather than folded in here, so this stays scoped to
SimulationPod.

## Consequences

- Every SimulationPod attempt going forward carries real, inspectable
  telemetry — `ace view <attempt>.py` shows exactly what `TDDCycleRunner`/
  Reflector saw at the time, not a re-derived approximation.
- `ace view <attempt>.py --video` produces a real, playable `.mp4` with zero
  display dependency — verified live under WSL (no X server) against a real
  `TactilePegInHoleScenario` attempt.
- `ace view` without `--video` needs zero new dependencies — `imageio`/
  `imageio-ffmpeg` are only imported inside `render_attempt_video`, and
  none of the scenario modules import `pybullet` at module level either, so
  `resolve_attempt` alone works even without the `simulation` extra
  installed.
- `demos/demo_simulation_pod_gui.py`'s behavior is unchanged — it now
  imports `SCENARIOS`/`load_controller_from_file` from the shared module
  instead of defining them inline, confirmed via its own `--help`/manual
  invocation still working identically.
