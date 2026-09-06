# ADR 005 — Cold-start model calibration, and why the Capability Broker stays unwired

**Status:** Accepted
**Date:** 2026-09-06

## Context

Issue #5 asked whether `CapabilityRegistry`/`BrokerAdvisor`
(`src/broker/capability_registry.py`, `src/broker/advisor.py`) — real,
unit-tested, but never called from any live path — "earn a live call site."
The concrete gap that motivated writing them: `AdaptiveBroker.route_task()`
(`src/broker/adaptive_broker.py`) only scores candidates that already have
real audit history. `PerformanceAggregator.get_all_agent_metrics()` groups
`CYCLE_COMPLETED` events by `actor_id`, so a model with zero history is never
even a key in the dict it returns — `route_task`'s candidate loop only ever
iterates that dict. A brand-new model added to `candidate_models:` is
architecturally unreachable by scoring, not merely under-scored, and can only
ever be picked via the first-candidate fallback.

`CapabilityRegistry` (declared proficiency, not earned track record) was one
way to let such a model compete from day one. Investigating it turned up two
problems:

1. **No live registration path exists for the models that matter here.** The
   only production caller of `CapabilityRegistry.register()` is
   `EffGenAdapter._sync_agents()` (`src/broker/effgen_adapter.py`), which is
   itself unwired (only reachable from the manual `scripts/e2e_broker_test.py`
   demo, and listed in `README.md`'s roadmap as "Planned," not shipped). It's
   also scoped to a different kind of agent — an `EffGenAgentConfig` with an
   `endpoint`/MCP semantics/team membership — not a plain
   `"<provider>/<model>"` ref like the ones `candidate_models:` actually
   contains. Wiring cold-start routing through it would mean building an
   entirely new declaration mechanism first (e.g. a `.ace/config.yaml` block
   a human fills in by hand), not just adding a call site.
2. **Wiring it into `AdaptiveBroker` for real is real surgery to a live,
   already-shipped routing path**, not "add a call site": `route_task`'s
   candidate-building loop would need to union `all_metrics` with registry
   entries, `_calculate_score` would need a new scoring branch for candidates
   with no `AgentPerformanceMetrics`, and — the part that gets genuinely
   awkward — a policy would be needed for when a one-time declared score
   stops being authoritative once real audit history starts accumulating
   (otherwise a single hand-typed guess outlives hundreds of real runs).

`BrokerAdvisor`/`HumanDecisionInterface` turned out to be solving a different
problem entirely: team formation (`find_balanced_team` — "which *combination*
of agents jointly covers these capabilities") and human-in-the-loop,
identity-blind advisory ("here's who's rated for X, you choose"). Neither
`ace tdd` nor `ace project` builds with a team of models, and neither pauses
for a human to pick between recommendations — both are fully automated CLI
runs. This subsystem has no live consumer today, independent of the
cold-start question.

## Decision

**Solve the actual named problem — a new candidate can't compete — by giving
it one real audit data point instead of a declared one.**
`route_model()` (`src/broker/model_router.py`, the one shared entry point
already used by `ace tdd`, `ace project` (#40), and MCP
`build_feature`/`build_feature_ensemble`) now runs one throwaway, real,
sandboxed TDD cycle against a small fixed calibration task
(`src/broker/calibration.py::calibrate_cold_start_models`) for any candidate
with zero audit history, before routing. That cycle already emits a normal
`CYCLE_COMPLETED` event via the existing `TDDCycleRunner`/`PolyglotTDDRunner`
audit wiring (`actor_id=model_id`) — **no changes were needed to
`AdaptiveBroker`, `PerformanceAggregator`, or `_calculate_score`.** From that
point on the model is indistinguishable from any other audited model to the
existing, unmodified scoring pipeline, and its score keeps updating with every
real run after that — no staleness problem, because it was never treated as
authoritative in the first place, just a first data point.

Whether the calibration task (a trivial `add(a, b)` function) passes or
fails, a real signal gets recorded either way: a model that can't solve it
legitimately should score low, not remain invisible.

`route_model()` gained a `calibrate_cold_start: bool = True` escape hatch for
callers who don't want the one-time extra sandboxed-run latency; no existing
caller needed to change.

**`CapabilityRegistry`/`BrokerAdvisor`/`HumanDecisionInterface`/
`EffGenAdapter` stay unwired.** Their differentiated value — team formation
and human-in-the-loop capability advisory — has no live consumer anywhere in
this codebase. Per this repo's own stated principle (echoed in issue #40's
scoping notes): don't build capability declarations speculatively without a
concrete consumer. If a team-based build mode or a human-in-the-loop CLI flow
is ever added, this ADR's reasoning should be revisited — the subsystem
itself doesn't need to change, only find something that actually calls it.

## Consequences

- Adding a new model to `candidate_models:` now costs one extra sandboxed TDD
  cycle the first time it's routed, then behaves exactly like any other
  audited model forever after. No config change required to get this.
- `AdaptiveBroker`'s scoring model stays single-source-of-truth (audit
  history only) — no second, declared-capability scoring path to keep in
  sync or reconcile against real outcomes.
- `CapabilityRegistry`/`BrokerAdvisor`/`HumanDecisionInterface`/
  `EffGenAdapter` remain exactly as before: real, tested, unwired. This ADR
  is the first design record explaining *why*, closing out issue #5's own
  "decide whether they earn a live call site" question for the foreseeable
  future rather than leaving it an open, undocumented gap.
- The calibration task (`add(a, b)`) is deliberately trivial and Python-only,
  matching the ensemble build path's own Python-only scope
  (`src/agents/ensemble_build.py`) — it is a smoke test for "can this model
  produce working code at all," not a capability benchmark. It doesn't
  attempt to calibrate per-task-type or per-complexity signal; those refine
  naturally from real usage afterward, same as any other model.
