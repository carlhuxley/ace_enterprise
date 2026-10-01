"""
TDDCycleRunner — orchestrates RED → GREEN → REFACTOR for one feature.

Handles GREEN retries with error feedback and aborts on security/policy failures.

Optional learning loop: if reflector + curator + playbook_id are provided, a
Reflector/Curator pass runs after each successful cycle to extract reusable
patterns and write them back to the playbook. It also runs on a *stagnant*
GREEN failure -- every retry attempt spent without ever passing or hitting a
hard abort (see _is_stagnant) -- so a genuinely exhausted attempt still
teaches the playbook something, not just a winning one. A single off-target
first try that a normal retry could still fix is not stagnation and does not
trigger learning.

Optional audit trail: if audit_client is provided, TEST_GENERATED,
IMPLEMENTATION_GENERATED, PATTERN_LEARNED, and CYCLE_COMPLETED events are
emitted onto the hash-chained audit log (see src/audit/), same events
AutonomousTDDAgent used to emit natively.
"""
import dataclasses
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from src.agents.language_pod import PhaseResult, PodSpec, TokenUsage
from src.audit.schemas import AuditEventType as _AuditEventType
from src.ui.broadcaster import broadcast_event, set_current_phase
from src.ui.events import ExecutionStreamEvent, PlaybookDeltaEvent

logger = logging.getLogger(__name__)

# Fallback actor_id when no model_id is supplied (e.g. older callers/tests).
# PerformanceAggregator groups metrics BY actor_id, so every real caller
# should pass a model_id that actually identifies the LLM in use --
# otherwise every agent/model routed through this runner collapses into one
# indistinguishable bucket and AdaptiveBroker has nothing to route between.
_ACTOR_ID = "tdd-agent-cycle-runner"


@dataclass
class CycleResult:
    """Outcome of a complete TDD cycle."""

    success: bool
    feature_requirement: str
    red_result: PhaseResult
    green_result: PhaseResult
    refactor_result: PhaseResult | None
    green_attempts: int
    token_usage: list[TokenUsage]
    error: str | None = None
    learned_bullets: list = field(default_factory=list)  # list[DeltaBullet]


class TDDCycleRunner:
    """
    Runs one complete TDD cycle: RED → GREEN (with retry) → REFACTOR.

    GREEN is retried up to max_green_attempts times, passing the previous
    failure output back to the pod so the LLM can learn from the error.
    Any security or policy failure (ForbiddenImport, SecurityBreach, Security gate)
    aborts the cycle immediately without retrying.

    Optional:
      experiment_logger  — persists each cycle via ExperimentLogger.log_tdd_cycle()
      reflector          — Reflector instance; runs after successful cycles
      curator            — Curator instance; synthesises bullets from reflector output
      playbook_id        — target playbook for curator writes (required when using
                           reflector/curator; defaults to "podman_harness")
      audit_client       — emits TEST_GENERATED/IMPLEMENTATION_GENERATED/
                           PATTERN_LEARNED/CYCLE_COMPLETED events (e.g. LocalAuditClient)
      max_red_attempts   — retries RED generation/parsing failures that never
                           reached the container (e.g. the LLM's own code
                           doesn't parse) -- distinct from a normal RED PASS
                           result (test correctly fails with no impl yet),
                           which is never retried. Security/policy aborts are
                           never retried either.
      escalation_llm_client, escalation_model_id — repair-ceiling escalation
                           (#40, extended from the batch path/ModuleTDDBuilder
                           to here): one extra GREEN attempt against this
                           stronger model after max_green_attempts is
                           exhausted. None (the default) disables it entirely.
    """

    def __init__(
        self,
        pod,
        max_green_attempts: int = 3,
        experiment_logger=None,
        playbook_id: str = "podman_harness",
        reflector=None,
        curator=None,
        audit_client=None,
        max_red_attempts: int = 2,
        team_id: str | None = None,
        model_id: str | None = None,
        task_type: str | None = None,
        escalation_llm_client=None,
        escalation_model_id: str | None = None,
    ) -> None:
        self._pod = pod
        self._max_green_attempts = max_green_attempts
        self._experiment_logger = experiment_logger
        self._playbook_id = playbook_id
        self._reflector = reflector
        self._curator = curator
        self._audit_client = audit_client
        self._max_red_attempts = max_red_attempts
        # Repair-ceiling escalation (#40): None (the default) disables it
        # entirely, identical to today's behavior.
        self._escalation_llm_client = escalation_llm_client
        self._escalation_model_id = escalation_model_id
        # Stamped into every bullet Curator writes (see DeltaBullet.team_id /
        # Curator._parse_synthesis) so ContextScorer.score_team()'s RANK
        # dimension has real data to score against instead of always hitting
        # the "no team context" neutral path.
        self._team_id = team_id
        # Real model/agent identity (e.g. "openrouter/deepseek/deepseek-v4"
        # or "claude-cli"), used as the audit actor_id so
        # PerformanceAggregator.get_all_agent_metrics() can distinguish
        # agents instead of collapsing everything into the fallback
        # _ACTOR_ID bucket.
        self._model_id = model_id or _ACTOR_ID
        # e.g. the target language ("python"/"typescript"/"go") -- the only
        # task-classification signal currently available at this layer.
        self._task_type = task_type

    def _run_phase(self, phase: str, call) -> PhaseResult:
        """Wraps one `self._pod.run_red/run_green/run_refactor(...)` call
        with before/after `ExecutionStreamEvent` broadcasts for the live
        dashboard (`ace dashboard`). `TDDCycleRunner.run()` is the only real
        caller of any pod's phase methods (confirmed via repo-wide grep) --
        one wrapper here covers every pod (Python/Go/TypeScript/Simulation)
        and every retry/escalation attempt uniformly, with no per-pod code.
        `call` is a zero-arg callable so each call site keeps its own exact
        arguments (retry_spec, escalate=True, ...) unchanged.

        set_current_phase() tags this thread for the duration of `call()` so
        the streaming helper in src/agents/podman_runner.py (several
        call-stack levels below, inside send_pulse()) can broadcast
        incremental "chunk" events under the right phase without phase
        needing to be threaded through PodmanOrchestrator.pulse()/
        ContainerRunner.send_pulse()'s signatures. Reset in `finally` so a
        later send_pulse() call on this thread outside any _run_phase()
        (if one ever existed) doesn't inherit a stale phase tag."""
        set_current_phase(phase)
        try:
            broadcast_event(ExecutionStreamEvent(phase=phase, status="started"))
            result = call()
            broadcast_event(ExecutionStreamEvent(
                phase=phase, status="completed",
                stdout_chunk=result.output or result.error or "",
                exit_code=0 if result.passed else 1,
            ))
            return result
        finally:
            set_current_phase(None)

    def run(self, spec: PodSpec) -> CycleResult:
        cycle_start = time.monotonic()
        token_start = len(self._pod.token_usage())

        # --- RED ---
        # All three pods return PhaseResult(output="", error=str(exc)) for
        # failures during generation/parsing/import-checking (before
        # orchestrator.pulse() is ever called) -- commit_to_disk() never ran,
        # so there's no test file yet. Unlike a security/policy abort or a
        # normal RED result (test correctly fails in the container with no
        # impl yet, which always has real pytest/vitest/go output), this is
        # often just LLM output-formatting noise (e.g. an unclosed markdown
        # fence, a stray non-ASCII character breaking the parser) worth one
        # retry before giving up -- GREEN already gets this treatment.
        red_result = self._run_phase("RED", lambda: self._pod.run_red(spec))
        for _ in range(self._max_red_attempts - 1):
            red_never_pulsed = red_result.output == "" and bool(red_result.error)
            if _is_abort(red_result) or not red_never_pulsed:
                break
            red_result = self._run_phase("RED", lambda: self._pod.run_red(spec))

        red_never_pulsed = red_result.output == "" and bool(red_result.error)
        if _is_abort(red_result) or red_never_pulsed:
            reason = red_result.error if _is_abort(red_result) else (
                red_result.error or "RED did not write a test file"
            )
            cycle_result = CycleResult(
                success=False,
                feature_requirement=spec.feature_requirement,
                red_result=red_result,
                green_result=PhaseResult(passed=False, output="", error="skipped"),
                refactor_result=None,
                green_attempts=0,
                token_usage=self._pod.token_usage()[token_start:],
                error=f"RED aborted: {reason}",
            )
            self._log(spec, cycle_result)
            self._emit_cycle_completed(spec, cycle_result, time.monotonic() - cycle_start)
            return cycle_result

        self._emit(_AuditEventType.TEST_GENERATED, {
            "test_name": spec.test_file.stem, "cycle": spec.cycle_number,
        })

        # --- GREEN with retries ---
        green_result = PhaseResult(passed=False, output="", error=None)
        green_attempts = 0
        error_feedback = ""
        for _ in range(self._max_green_attempts):
            green_attempts += 1
            retry_spec = dataclasses.replace(spec, error_output=error_feedback)
            green_result = self._run_phase("GREEN", lambda rs=retry_spec: self._pod.run_green(rs))
            if green_result.passed or _is_abort(green_result):
                break
            error_feedback = green_result.output or green_result.error or ""

        # Repair-ceiling escalation (#40), extended from the batch path to
        # here: exactly one extra attempt against a stronger model, only
        # once the normal retry budget above is exhausted, only if one was
        # configured, never for an abort (matches the loop's own break
        # condition). Reuses `retry_spec` as the loop's last iteration left
        # it -- already carries the last failure's own error_output (e.g.
        # a PROTECTED_SIGNATURE_CHANGED diff), not a blank slate.
        if (
            not green_result.passed
            and not _is_abort(green_result)
            and self._escalation_llm_client is not None
        ):
            logger.warning(
                "TDDCycleRunner: GREEN retry budget exhausted, escalating %s -> %s for cycle %s",
                self._model_id, self._escalation_model_id, spec.cycle_number,
            )
            green_attempts += 1
            green_result = self._run_phase("GREEN", lambda rs=retry_spec: self._pod.run_green(rs, escalate=True))
            logger.warning(
                "TDDCycleRunner: escalated attempt %s",
                "succeeded" if green_result.passed else "also failed",
            )
            if self._audit_client is not None:
                try:
                    self._audit_client.emit_simple(
                        event_type=_AuditEventType.ESCALATION_TRIGGERED,
                        actor_id=self._escalation_model_id,
                        payload={
                            "cycle": spec.cycle_number,
                            "from_model": self._model_id,
                            "to_model": self._escalation_model_id,
                            "success": green_result.passed,
                        },
                        playbook_id=self._playbook_id,
                    )
                except Exception as exc:
                    logger.warning(f"TDDCycleRunner: escalation audit emit failed: {exc}")

        if not green_result.passed:
            cycle_result = CycleResult(
                success=False,
                feature_requirement=spec.feature_requirement,
                red_result=red_result,
                green_result=green_result,
                refactor_result=None,
                green_attempts=green_attempts,
                token_usage=self._pod.token_usage()[token_start:],
                error=green_result.error or "GREEN phase failed",
            )
            # _learn() already handles a FAILED outcome internally (see
            # EnvironmentFeedback.result below); it was only ever gated by
            # the success check this branch used to return before reaching.
            if _is_stagnant(green_attempts, self._max_green_attempts, green_result):
                learned = self._learn(spec, cycle_result)
                cycle_result = dataclasses.replace(cycle_result, learned_bullets=learned)
            self._log(spec, cycle_result)
            self._emit_cycle_completed(spec, cycle_result, time.monotonic() - cycle_start)
            return cycle_result

        self._emit(_AuditEventType.IMPLEMENTATION_GENERATED, {
            "file": str(spec.implementation_file), "cycle": spec.cycle_number,
        })

        # --- REFACTOR ---
        refactor_result = self._run_phase("REFACTOR", lambda: self._pod.run_refactor(spec))

        cycle_result = CycleResult(
            success=refactor_result.passed,
            feature_requirement=spec.feature_requirement,
            red_result=red_result,
            green_result=green_result,
            refactor_result=refactor_result,
            green_attempts=green_attempts,
            token_usage=self._pod.token_usage()[token_start:],
            error=None if refactor_result.passed else (refactor_result.error or "REFACTOR phase failed"),
        )

        # Also runs on a stagnant GREEN failure (see the early-return branch
        # above) — this branch is the ordinary post-success path.
        if cycle_result.green_result.passed:
            learned = self._learn(spec, cycle_result)
            cycle_result = dataclasses.replace(cycle_result, learned_bullets=learned)

        self._log(spec, cycle_result)
        self._emit_cycle_completed(spec, cycle_result, time.monotonic() - cycle_start)
        return cycle_result

    # ------------------------------------------------------------------
    # Learning loop (Reflector → Curator → playbook write)
    # ------------------------------------------------------------------

    def _learn(self, spec: PodSpec, result: CycleResult) -> list:
        """Run Reflector + Curator and write delta bullets to the playbook."""
        if self._reflector is None or self._curator is None:
            return []

        from src.storage.schemas import EnvironmentFeedback, GeneratorOutput, TaskInput

        total_tokens = sum(u.input_tokens + u.output_tokens for u in result.token_usage)
        env_result = "SUCCESS" if result.success else "FAILED"

        task = TaskInput(
            id=f"tdd_{spec.cycle_number}_{uuid.uuid4().hex[:8]}",
            query=spec.feature_requirement,
            type="tdd_cycle",
        )
        gen_output = GeneratorOutput(
            trajectory=_read_if_exists(spec.test_file),
            solution=_read_if_exists(spec.implementation_file),
            bullets_used=[],
            bullet_feedback={},
            latency_ms=0,
            tokens_used=total_tokens,
        )
        feedback = result.error
        protected = getattr(self._pod, "protected_symbols", lambda: None)()
        if protected:
            # Causal invariant hierarchy: a real experiment found the
            # Reflector, given only a bare "missing required argument"
            # error, plausibly but wrongly diagnosing a schema-driven
            # module's contract-fixed dataclasses as needing defaults --
            # canonizing that into the playbook and fighting the
            # ProtectedShape lock. Naming the protected symbols and stating
            # the causal direction explicitly (a construction/validation
            # error is always a caller bug, never a reason to relax the
            # contract) heads that off at the source, since this text
            # reaches Reflector._build_analysis_prompt verbatim.
            feedback = (
                f"IMMUTABLE CONTRACT CONSTRAINT: {', '.join(protected)} are "
                "fixed by this module's formal contract -- their fields, "
                "signatures, and defaults cannot be changed. A missing-"
                "required-argument or validation error here is ALWAYS a bug "
                "in the calling test or implementation code (e.g. a test "
                "fixture omitting a required field), NEVER a reason to add "
                "defaults, loosen a type, or otherwise relax these "
                "definitions.\n\n" + (feedback or "")
            )
        env_feedback = EnvironmentFeedback(
            result=env_result,
            actual=result.green_result.output or "",
            feedback=feedback,
        )

        try:
            reflector_output = self._reflector.reflect(task, gen_output, env_feedback)
            curator_output = self._curator.curate(
                reflector_output,
                self._playbook_id,
                task_context={
                    "requirement": spec.feature_requirement,
                    "cycle": spec.cycle_number,
                    "team_id": self._team_id,
                },
            )
            self._curator.apply_updates(self._playbook_id, curator_output)
            # getattr, not a direct attribute access: not every Reflector's
            # output is a real storage.schemas.ReflectorOutput (e.g.
            # hand-rolled test doubles) -- broadcasting for the live
            # dashboard must never be able to break the actual learn pass
            # (writing bullets to the playbook) just because a field is
            # missing.
            root_cause = getattr(reflector_output, "root_cause", "") or ""
            for bullet in curator_output.delta_bullets:
                broadcast_event(PlaybookDeltaEvent(
                    bullet_content=bullet.content,
                    bullet_section=bullet.section,
                    root_cause=root_cause,
                    cycle_number=spec.cycle_number,
                ))
            self._persist_reflection(spec, result, reflector_output, curator_output)
            logger.info(
                f"TDDCycleRunner: wrote {len(curator_output.delta_bullets)} "
                f"bullet(s) to playbook '{self._playbook_id}'"
            )
            if self._audit_client is not None:
                for bullet in curator_output.delta_bullets:
                    self._emit(_AuditEventType.PATTERN_LEARNED, {
                        "section": bullet.section, "content_hash": bullet.content_hash,
                    })
            return curator_output.delta_bullets
        except Exception as exc:
            logger.warning(f"TDDCycleRunner: learning step failed: {exc}")
            return []

    def _persist_reflection(
        self, spec: PodSpec, result: CycleResult, reflector_output, curator_output,
    ) -> Path | None:
        """Persist Reflector's diagnosis + Curator's delta bullets to a
        sibling JSON file keyed by attempt identity (#46) -- previously
        produced fresh every cycle, used once to write the playbook, and
        then discarded, with no way to look back at *why* an attempt
        succeeded/failed after the fact.

        Pod-agnostic: every LanguagePod's PodSpec carries
        implementation_file, so this needs no pod-specific archive to key
        off of. Written to implementation_file.parent/"attempts"/
        "{stem}_cycle{N}.reflection.json" -- for SimulationPod specifically,
        this stem is the PREFIX of its own finer-grained
        {stem}_cycle{N}_{phase}_attempt{M} archive names (see
        simulation_pod.py's _archive_attempt): one reflection covers a
        whole cycle's attempts, not one specific numbered attempt, since
        _learn() only ever runs once per TDDCycleRunner.run() call
        regardless of how many attempts that pod archived internally.

        Best-effort: a write failure here must never lose the playbook
        update _learn() already applied (see the outer try/except).
        """
        try:
            attempts_dir = spec.implementation_file.parent / "attempts"
            attempts_dir.mkdir(parents=True, exist_ok=True)
            stem = f"{spec.implementation_file.stem}_cycle{spec.cycle_number}"
            path = attempts_dir / f"{stem}.reflection.json"
            payload = {
                "cycle": spec.cycle_number,
                "success": result.success,
                "feature_requirement": spec.feature_requirement,
                "reflector": {
                    "error_identification": reflector_output.error_identification,
                    "root_cause": reflector_output.root_cause,
                    "correct_approach": reflector_output.correct_approach,
                    "key_insight": reflector_output.key_insight,
                    "code_invariant": reflector_output.code_invariant,
                },
                "curator": {
                    "reasoning": curator_output.reasoning,
                    "delta_bullets": [b.model_dump() for b in curator_output.delta_bullets],
                },
            }
            path.write_text(json.dumps(payload, indent=2))
            return path
        except Exception as exc:
            logger.warning(f"TDDCycleRunner: reflection persistence failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------

    def _emit(self, event_type, payload: dict) -> None:
        if self._audit_client is None:
            return
        try:
            self._audit_client.emit_simple(
                event_type=event_type,
                actor_id=self._model_id,
                payload=payload,
                playbook_id=self._playbook_id,
            )
        except Exception as exc:
            logger.warning(f"TDDCycleRunner: audit emit failed: {exc}")

    def _emit_cycle_completed(
        self, spec: PodSpec, result: CycleResult, elapsed_seconds: float
    ) -> None:
        # cost/quality_score/complexity are deliberately omitted -- no real
        # pricing table or quality-scoring instrument exists in this pipeline
        # yet, and PerformanceAggregator/AdaptiveBroker should never route on
        # fabricated numbers.
        self._emit(_AuditEventType.CYCLE_COMPLETED, {
            "cycle": spec.cycle_number,
            "success": result.success,
            "bullets_learned": len(result.learned_bullets),
            "elapsed_seconds": elapsed_seconds,
            "task_type": self._task_type,
            # green_attempts==1 means GREEN passed (or was abandoned) on the
            # first try -- the "first-pass" signal PlaybookReliabilityAnalyzer
            # correlates against retrieved_bullet_ids for causal uplift.
            "green_attempts": result.green_attempts,
            "retrieved_bullet_ids": result.green_result.retrieved_bullet_ids or [],
        })

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, spec: PodSpec, result: CycleResult) -> None:
        if self._experiment_logger is None:
            return
        total_tokens = sum(u.input_tokens + u.output_tokens for u in result.token_usage)
        test_code = _read_if_exists(spec.test_file)
        impl_code = _read_if_exists(spec.implementation_file)
        # Most recent TokenUsage entry carries the freshest model attribution
        # (LanguagePod._intercept_tokens implementations record it per LLM
        # call); None for pods/clients that predate this or made no call.
        actual_model = requested_model = provider = None
        for usage in reversed(result.token_usage):
            if usage.actual_model or usage.provider:
                actual_model = usage.actual_model
                requested_model = usage.requested_model
                provider = usage.provider
                break
        self._experiment_logger.log_tdd_cycle(
            cycle_number=spec.cycle_number,
            requirement=spec.feature_requirement,
            test_name=spec.test_file.stem,
            test_code=test_code,
            implementation_code=impl_code,
            red_passed=result.red_result.passed,
            green_passed=result.green_result.passed,
            red_output=result.red_result.output or "",
            green_output=result.green_result.output or "",
            learned_bullets=[
                {"content": b.content, "section": b.section}
                for b in result.learned_bullets
            ],
            playbook_id=self._playbook_id,
            tokens_used=total_tokens,
            actual_model=actual_model,
            requested_model=requested_model,
            provider=provider,
            retry_count=result.green_attempts,
            harness_metadata={
                "green_attempts": result.green_attempts,
                "refactor_passed": result.refactor_result.passed if result.refactor_result else None,
                "error": result.error,
                "bullets_learned": len(result.learned_bullets),
            },
        )


def _read_if_exists(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def _is_stagnant(green_attempts: int, max_green_attempts: int, green_result: PhaseResult) -> bool:
    """True when GREEN exhausted its full retry budget without ever passing
    or hitting a hard abort -- a genuinely stuck attempt worth reflecting on,
    as opposed to a single off-target try a normal retry could still fix.
    This is pod-agnostic: it only needs the attempt count TDDCycleRunner
    already tracks, not any pod-specific telemetry/diagnosis format."""
    return green_attempts >= max_green_attempts and not _is_abort(green_result)


def _is_abort(result: PhaseResult) -> bool:
    """True for security/policy failures that cannot be fixed by retry."""
    if result.error is None:
        return False
    for prefix in (
        "ForbiddenImport:", "SecurityBreach:", "Security gate:",
        # Container infrastructure failures — no point retrying with LLM
        "Error: can only create exec sessions",
        "Error: no such container",
        "vitest timed out",
    ):
        if result.error.startswith(prefix):
            return True
    return False
