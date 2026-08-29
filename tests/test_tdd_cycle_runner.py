"""Tests for TDDCycleRunner (ace_enterprise-2qm).

Uses controlled pod doubles so we can drive exact pass/fail sequences
without touching the container or LLM.
"""
import dataclasses
from pathlib import Path

import pytest

from src.agents.language_pod import PhaseResult, PodSpec, TokenUsage
from src.agents.tdd_cycle_runner import CycleResult, TDDCycleRunner


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class ControlledPod:
    """Pod double: RED always fails; GREEN passes on Nth attempt; REFACTOR passes."""

    def __init__(self, green_pass_on: int = 1, refactor_passes: bool = True):
        self._green_pass_on = green_pass_on
        self._green_count = 0
        self._refactor_passes = refactor_passes
        self.green_specs: list[PodSpec] = []

    def run_red(self, spec: PodSpec) -> PhaseResult:
        return PhaseResult(passed=False, output="test fails: no impl", error=None)

    def run_green(self, spec: PodSpec) -> PhaseResult:
        self.green_specs.append(spec)
        self._green_count += 1
        if self._green_count >= self._green_pass_on:
            return PhaseResult(passed=True, output="1 passed", error=None)
        return PhaseResult(passed=False, output="AssertionError: expected 3 got 0", error=None)

    def run_refactor(self, spec: PodSpec) -> PhaseResult:
        if self._refactor_passes:
            return PhaseResult(passed=True, output="1 passed", error=None)
        return PhaseResult(passed=False, output="FAILED", error="refactor broke tests")

    def token_usage(self) -> list[TokenUsage]:
        return []


class AbortingRedPod(ControlledPod):
    """RED returns a forbidden import error → should abort cycle."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.red_calls = 0

    def run_red(self, spec: PodSpec) -> PhaseResult:
        self.red_calls += 1
        return PhaseResult(passed=False, output="", error="ForbiddenImport: os")


class RedRetryPod(ControlledPod):
    """RED fails before-pulse on the first attempt, succeeds for real on the second."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.red_calls = 0

    def run_red(self, spec: PodSpec) -> PhaseResult:
        self.red_calls += 1
        if self.red_calls == 1:
            return PhaseResult(passed=False, output="", error="SyntaxError: unexpected EOF")
        return PhaseResult(passed=False, output="test fails: no impl", error=None)


class RedFailsBeforePulsePod(ControlledPod):
    """RED fails during generation/parsing, before ever reaching the
    container -- output="" is what all three real pods (Python/TS/Go) return
    for this case (e.g. a plain SyntaxError from the LLM's own code, not a
    security/policy issue matched by _is_abort's prefix list)."""

    def run_red(self, spec: PodSpec) -> PhaseResult:
        return PhaseResult(passed=False, output="", error="invalid character '—' (U+2014)")


class AbortingGreenPod(ControlledPod):
    """GREEN returns a security breach → should abort without further retries."""

    def run_green(self, spec: PodSpec) -> PhaseResult:
        self.green_specs.append(spec)
        return PhaseResult(passed=False, output="", error="SecurityBreach: hash mismatch")


class TokenPod(ControlledPod):
    """Accumulates one TokenUsage record per phase call."""

    def __init__(self, actual_model=None, requested_model=None, provider=None):
        super().__init__()
        self._usage: list[TokenUsage] = []
        self._actual_model = actual_model
        self._requested_model = requested_model
        self._provider = provider

    def _usage_kwargs(self, spec: PodSpec, input_tokens: int) -> dict:
        return dict(
            cycle_number=spec.cycle_number,
            input_tokens=input_tokens,
            output_tokens=0,
            actual_model=self._actual_model,
            requested_model=self._requested_model,
            provider=self._provider,
        )

    def run_red(self, spec: PodSpec) -> PhaseResult:
        self._usage.append(TokenUsage(**self._usage_kwargs(spec, 50)))
        return super().run_red(spec)

    def run_green(self, spec: PodSpec) -> PhaseResult:
        self._usage.append(TokenUsage(**self._usage_kwargs(spec, 150)))
        return super().run_green(spec)

    def run_refactor(self, spec: PodSpec) -> PhaseResult:
        self._usage.append(TokenUsage(**self._usage_kwargs(spec, 80)))
        return super().run_refactor(spec)

    def token_usage(self) -> list[TokenUsage]:
        return list(self._usage)


def _spec(tmp_path: Path) -> PodSpec:
    return PodSpec(
        feature_requirement="add two numbers",
        test_file=tmp_path / "test_add.py",
        implementation_file=tmp_path / "add.py",
        cycle_number=1,
    )


# ---------------------------------------------------------------------------
# Behavior 1: full happy-path RED → GREEN → REFACTOR (tracer bullet)
# ---------------------------------------------------------------------------

def test_full_cycle_success(tmp_path):
    runner = TDDCycleRunner(ControlledPod())
    result = runner.run(_spec(tmp_path))

    assert isinstance(result, CycleResult)
    assert result.success is True
    assert result.red_result.passed is False
    assert result.green_result.passed is True
    assert result.refactor_result is not None
    assert result.refactor_result.passed is True


# ---------------------------------------------------------------------------
# Behavior 2: RED abort (ForbiddenImport) → no GREEN attempted
# ---------------------------------------------------------------------------

def test_red_abort_skips_green_and_refactor(tmp_path):
    pod = AbortingRedPod()
    runner = TDDCycleRunner(pod)
    result = runner.run(_spec(tmp_path))

    assert result.success is False
    assert result.green_attempts == 0
    assert result.refactor_result is None
    assert "RED aborted" in (result.error or "")


def test_red_failure_before_pulse_also_aborts_without_wasting_green_attempts(tmp_path):
    """Regression: a RED failure with no error prefix _is_abort recognizes
    (e.g. a raw SyntaxError) used to fall through to GREEN, which would then
    burn every retry pulsing a test file that was never actually written."""
    pod = RedFailsBeforePulsePod()
    runner = TDDCycleRunner(pod)
    result = runner.run(_spec(tmp_path))

    assert result.success is False
    assert result.green_attempts == 0
    assert len(pod.green_specs) == 0
    assert result.refactor_result is None
    assert "RED aborted" in (result.error or "")
    assert "invalid character" in (result.error or "")


def test_red_retries_before_pulse_failure_and_then_succeeds(tmp_path):
    pod = RedRetryPod()
    runner = TDDCycleRunner(pod, max_red_attempts=2)
    result = runner.run(_spec(tmp_path))

    assert pod.red_calls == 2
    assert result.success is True  # ControlledPod's GREEN passes on first attempt


def test_red_retry_exhausted_still_aborts(tmp_path):
    pod = RedFailsBeforePulsePod()  # always fails before-pulse
    runner = TDDCycleRunner(pod, max_red_attempts=2)
    result = runner.run(_spec(tmp_path))

    assert result.success is False
    assert len(pod.green_specs) == 0
    assert "RED aborted" in (result.error or "")


def test_red_never_retries_a_security_abort(tmp_path):
    pod = AbortingRedPod()
    runner = TDDCycleRunner(pod, max_red_attempts=3)
    runner.run(_spec(tmp_path))
    assert pod.red_calls == 1  # security/policy aborts skip the retry loop entirely


def test_red_failure_with_real_output_still_proceeds_to_green(tmp_path):
    """A normal RED failure (test ran for real in the container and failed
    as expected, e.g. ImportError with no impl yet) has real pytest/vitest/go
    output -- must NOT be mistaken for the no-pulse case above."""
    pod = ControlledPod()  # run_red returns output="test fails: no impl"
    runner = TDDCycleRunner(pod)
    result = runner.run(_spec(tmp_path))

    assert len(pod.green_specs) >= 1
    assert result.success is True


# ---------------------------------------------------------------------------
# Behavior 3: GREEN fails first attempt, succeeds on second
# ---------------------------------------------------------------------------

def test_green_retry_succeeds_on_second_attempt(tmp_path):
    runner = TDDCycleRunner(ControlledPod(green_pass_on=2))
    result = runner.run(_spec(tmp_path))

    assert result.success is True
    assert result.green_attempts == 2


# ---------------------------------------------------------------------------
# Behavior 4: GREEN exhausts all retries → success=False
# ---------------------------------------------------------------------------

def test_green_exhausts_retries_returns_failure(tmp_path):
    runner = TDDCycleRunner(ControlledPod(green_pass_on=999), max_green_attempts=3)
    result = runner.run(_spec(tmp_path))

    assert result.success is False
    assert result.green_attempts == 3
    assert result.refactor_result is None


# ---------------------------------------------------------------------------
# Behavior 5: REFACTOR fails → success=False with refactor_result populated
# ---------------------------------------------------------------------------

def test_refactor_failure_returns_success_false(tmp_path):
    runner = TDDCycleRunner(ControlledPod(refactor_passes=False))
    result = runner.run(_spec(tmp_path))

    assert result.success is False
    assert result.refactor_result is not None
    assert result.refactor_result.passed is False


# ---------------------------------------------------------------------------
# Behavior 6: GREEN abort (SecurityBreach) stops retries immediately
# ---------------------------------------------------------------------------

def test_green_abort_stops_retries(tmp_path):
    pod = AbortingGreenPod()
    runner = TDDCycleRunner(pod, max_green_attempts=3)
    result = runner.run(_spec(tmp_path))

    assert result.success is False
    assert len(pod.green_specs) == 1  # only one attempt made


# ---------------------------------------------------------------------------
# Behavior 7: error_output from failed GREEN is passed to next attempt
# ---------------------------------------------------------------------------

def test_error_output_threaded_to_retry(tmp_path):
    pod = ControlledPod(green_pass_on=2)
    runner = TDDCycleRunner(pod)
    runner.run(_spec(tmp_path))

    # First attempt gets blank error_output
    assert pod.green_specs[0].error_output == ""
    # Second attempt gets the output from the first failure
    assert "AssertionError" in pod.green_specs[1].error_output


# ---------------------------------------------------------------------------
# Behavior 8: token_usage from pod is captured in CycleResult
# ---------------------------------------------------------------------------

def test_token_usage_carried_in_result(tmp_path):
    runner = TDDCycleRunner(TokenPod())
    result = runner.run(_spec(tmp_path))

    # full cycle: red + green + refactor → 3 records
    assert len(result.token_usage) == 3
    assert result.token_usage[0].input_tokens == 50   # red
    assert result.token_usage[1].input_tokens == 150  # green
    assert result.token_usage[2].input_tokens == 80   # refactor


# ---------------------------------------------------------------------------
# Behavior 9: ExperimentLogger.log_tdd_cycle called after each cycle
# ---------------------------------------------------------------------------

def test_experiment_logger_called_on_success(tmp_path):
    calls = []

    class _Logger:
        def log_tdd_cycle(self, **kwargs):
            calls.append(kwargs)

    spec = _spec(tmp_path)
    spec.test_file.write_text("# test")
    spec.implementation_file.write_text("# impl")

    runner = TDDCycleRunner(ControlledPod(), experiment_logger=_Logger(), playbook_id="test-pb")
    runner.run(spec)

    assert len(calls) == 1
    c = calls[0]
    assert c["cycle_number"] == 1
    assert c["requirement"] == "add two numbers"
    assert c["green_passed"] is True
    assert c["red_passed"] is False
    assert c["playbook_id"] == "test-pb"
    assert c["retry_count"] == 1


def test_experiment_logger_receives_model_attribution(tmp_path):
    """Model identity captured by the pod's TokenUsage entries must reach
    log_tdd_cycle -- previously TDDCycleRunner._log() never passed
    actual_model/requested_model/provider even though ExperimentLogger
    always accepted them, so 93% of historical rows were unattributed."""
    calls = []

    class _Logger:
        def log_tdd_cycle(self, **kwargs):
            calls.append(kwargs)

    pod = TokenPod(
        actual_model="anthropic/claude-3.5-haiku",
        requested_model="anthropic/claude-3.5-haiku",
        provider="openrouter",
    )
    runner = TDDCycleRunner(pod, experiment_logger=_Logger())
    runner.run(_spec(tmp_path))

    assert len(calls) == 1
    assert calls[0]["actual_model"] == "anthropic/claude-3.5-haiku"
    assert calls[0]["requested_model"] == "anthropic/claude-3.5-haiku"
    assert calls[0]["provider"] == "openrouter"


def test_experiment_logger_model_attribution_absent_when_pod_reports_none(tmp_path):
    calls = []

    class _Logger:
        def log_tdd_cycle(self, **kwargs):
            calls.append(kwargs)

    runner = TDDCycleRunner(ControlledPod(), experiment_logger=_Logger())
    runner.run(_spec(tmp_path))

    assert calls[0]["actual_model"] is None
    assert calls[0]["requested_model"] is None
    assert calls[0]["provider"] is None


def test_experiment_logger_called_on_red_abort(tmp_path):
    calls = []

    class _Logger:
        def log_tdd_cycle(self, **kwargs):
            calls.append(kwargs)

    runner = TDDCycleRunner(AbortingRedPod(), experiment_logger=_Logger())
    runner.run(_spec(tmp_path))

    assert len(calls) == 1
    assert calls[0]["green_passed"] is False


def test_no_experiment_logger_does_not_raise(tmp_path):
    runner = TDDCycleRunner(ControlledPod())   # no logger
    result = runner.run(_spec(tmp_path))
    assert result.success is True


# ---------------------------------------------------------------------------
# Behavior 10: Reflector + Curator learning loop
# ---------------------------------------------------------------------------

class _FakeDeltaBullet:
    def __init__(self, content, section="strategies_and_hard_rules"):
        self.content = content
        self.section = section
        self.content_hash = f"fake-hash-{content[:8]}"


class _FakeReflectorOutput:
    pass


class _FakeCuratorOutput:
    def __init__(self, bullets):
        self.delta_bullets = bullets
        self.reasoning = "test reasoning"


class _SpyReflector:
    def __init__(self):
        self.calls = []

    def reflect(self, task, generator_output, environment_feedback):
        self.calls.append((task, generator_output, environment_feedback))
        return _FakeReflectorOutput()


class _SpyCurator:
    def __init__(self, bullets=None):
        self.curate_calls = []
        self.apply_calls = []
        self._bullets = bullets or [_FakeDeltaBullet("always use pathlib")]

    def curate(self, reflector_output, playbook_id, task_context=None):
        self.curate_calls.append((reflector_output, playbook_id, task_context))
        return _FakeCuratorOutput(self._bullets)

    def apply_updates(self, playbook_id, curator_output):
        self.apply_calls.append((playbook_id, curator_output))


def test_reflector_and_curator_called_on_success(tmp_path):
    reflector = _SpyReflector()
    curator = _SpyCurator()
    runner = TDDCycleRunner(
        ControlledPod(),
        reflector=reflector,
        curator=curator,
        playbook_id="test-pb",
    )
    result = runner.run(_spec(tmp_path))

    assert result.success is True
    assert len(reflector.calls) == 1
    assert len(curator.curate_calls) == 1
    assert curator.curate_calls[0][1] == "test-pb"
    assert len(curator.apply_calls) == 1


def test_team_id_included_in_curator_task_context(tmp_path):
    curator = _SpyCurator()
    runner = TDDCycleRunner(
        ControlledPod(), reflector=_SpyReflector(), curator=curator, team_id="payments",
    )
    runner.run(_spec(tmp_path))
    assert curator.curate_calls[0][2]["team_id"] == "payments"


def test_team_id_defaults_to_none_in_task_context(tmp_path):
    curator = _SpyCurator()
    runner = TDDCycleRunner(ControlledPod(), reflector=_SpyReflector(), curator=curator)
    runner.run(_spec(tmp_path))
    assert curator.curate_calls[0][2]["team_id"] is None


def test_learned_bullets_in_cycle_result(tmp_path):
    curator = _SpyCurator(bullets=[
        _FakeDeltaBullet("use dataclasses for value objects"),
        _FakeDeltaBullet("avoid mutable defaults"),
    ])
    runner = TDDCycleRunner(ControlledPod(), reflector=_SpyReflector(), curator=curator)
    result = runner.run(_spec(tmp_path))

    assert len(result.learned_bullets) == 2
    assert result.learned_bullets[0].content == "use dataclasses for value objects"


def test_learning_skipped_on_green_failure(tmp_path):
    reflector = _SpyReflector()
    curator = _SpyCurator()
    runner = TDDCycleRunner(
        ControlledPod(green_pass_on=999),
        max_green_attempts=1,
        reflector=reflector,
        curator=curator,
    )
    result = runner.run(_spec(tmp_path))

    assert result.success is False
    assert len(reflector.calls) == 0
    assert len(curator.curate_calls) == 0
    assert result.learned_bullets == []


def test_learning_skipped_on_red_abort(tmp_path):
    reflector = _SpyReflector()
    runner = TDDCycleRunner(AbortingRedPod(), reflector=reflector, curator=_SpyCurator())
    runner.run(_spec(tmp_path))
    assert len(reflector.calls) == 0


def test_learning_failure_does_not_crash_cycle(tmp_path):
    class _BrokenCurator(_SpyCurator):
        def curate(self, *args, **kwargs):
            raise RuntimeError("DB connection lost")

    runner = TDDCycleRunner(
        ControlledPod(),
        reflector=_SpyReflector(),
        curator=_BrokenCurator(),
    )
    result = runner.run(_spec(tmp_path))

    assert result.success is True          # cycle still succeeds
    assert result.learned_bullets == []    # bullets empty on error


def test_no_reflector_leaves_learned_bullets_empty(tmp_path):
    runner = TDDCycleRunner(ControlledPod())   # neither reflector nor curator
    result = runner.run(_spec(tmp_path))
    assert result.learned_bullets == []


# ---------------------------------------------------------------------------
# Behavior 11: audit trail (ace_enterprise -- ported from AutonomousTDDAgent's
# native audit emission, now optional via TDDCycleRunner(audit_client=...))
# ---------------------------------------------------------------------------

class _SpyAuditClient:
    def __init__(self):
        self.events = []

    def emit_simple(self, *, event_type, actor_id, payload, playbook_id=None):
        self.events.append(dict(
            event_type=event_type, actor_id=actor_id, payload=payload, playbook_id=playbook_id,
        ))
        return True


def test_no_audit_client_emits_nothing(tmp_path):
    # Default: audit_client=None must not raise and must emit nothing.
    runner = TDDCycleRunner(ControlledPod())
    result = runner.run(_spec(tmp_path))
    assert result.success is True


def test_emits_test_generated_after_red(tmp_path):
    audit = _SpyAuditClient()
    runner = TDDCycleRunner(ControlledPod(), audit_client=audit)
    runner.run(_spec(tmp_path))

    from src.audit.schemas import AuditEventType
    types = [e["event_type"] for e in audit.events]
    assert AuditEventType.TEST_GENERATED in types

def test_no_test_generated_event_on_red_abort(tmp_path):
    audit = _SpyAuditClient()
    runner = TDDCycleRunner(AbortingRedPod(), audit_client=audit)
    runner.run(_spec(tmp_path))

    from src.audit.schemas import AuditEventType
    types = [e["event_type"] for e in audit.events]
    assert AuditEventType.TEST_GENERATED not in types
    assert AuditEventType.CYCLE_COMPLETED in types


def test_emits_implementation_generated_after_green_passes(tmp_path):
    audit = _SpyAuditClient()
    runner = TDDCycleRunner(ControlledPod(), audit_client=audit)
    runner.run(_spec(tmp_path))

    from src.audit.schemas import AuditEventType
    types = [e["event_type"] for e in audit.events]
    assert AuditEventType.IMPLEMENTATION_GENERATED in types


def test_no_implementation_generated_event_when_green_never_passes(tmp_path):
    audit = _SpyAuditClient()
    runner = TDDCycleRunner(ControlledPod(green_pass_on=999), max_green_attempts=1, audit_client=audit)
    runner.run(_spec(tmp_path))

    from src.audit.schemas import AuditEventType
    types = [e["event_type"] for e in audit.events]
    assert AuditEventType.IMPLEMENTATION_GENERATED not in types


def test_emits_cycle_completed_with_success_and_bullets_learned(tmp_path):
    from src.storage.schemas import DeltaBullet

    audit = _SpyAuditClient()
    curator = _SpyCurator(bullets=[DeltaBullet(section="s", content="use pathlib")])
    runner = TDDCycleRunner(
        ControlledPod(), reflector=_SpyReflector(), curator=curator, audit_client=audit,
    )
    runner.run(_spec(tmp_path))

    from src.audit.schemas import AuditEventType
    completed = [e for e in audit.events if e["event_type"] == AuditEventType.CYCLE_COMPLETED]
    assert len(completed) == 1
    assert completed[0]["payload"]["success"] is True
    assert completed[0]["payload"]["bullets_learned"] == 1


def test_emits_pattern_learned_per_bullet(tmp_path):
    from src.storage.schemas import DeltaBullet

    audit = _SpyAuditClient()
    curator = _SpyCurator(bullets=[
        DeltaBullet(section="s1", content="use pathlib"),
        DeltaBullet(section="s2", content="avoid mutable defaults"),
    ])
    runner = TDDCycleRunner(
        ControlledPod(), reflector=_SpyReflector(), curator=curator, audit_client=audit,
    )
    runner.run(_spec(tmp_path))

    from src.audit.schemas import AuditEventType
    learned = [e for e in audit.events if e["event_type"] == AuditEventType.PATTERN_LEARNED]
    assert len(learned) == 2


def test_audit_events_include_playbook_id(tmp_path):
    audit = _SpyAuditClient()
    runner = TDDCycleRunner(ControlledPod(), playbook_id="my-playbook", audit_client=audit)
    runner.run(_spec(tmp_path))
    assert all(e["playbook_id"] == "my-playbook" for e in audit.events)


def test_audit_emit_failure_does_not_crash_cycle(tmp_path):
    class _BrokenAuditClient:
        def emit_simple(self, **kwargs):
            raise RuntimeError("audit db down")

    runner = TDDCycleRunner(ControlledPod(), audit_client=_BrokenAuditClient())
    result = runner.run(_spec(tmp_path))
    assert result.success is True


# ---------------------------------------------------------------------------
# Behavior 12: broker telemetry contract -- actor_id/elapsed_seconds/task_type
# must carry real data, since PerformanceAggregator (src/broker/) groups
# metrics BY actor_id and reads these exact payload keys. Before this fix,
# actor_id was a hardcoded constant regardless of model_id, so every model
# routed through TDDCycleRunner collapsed into one indistinguishable bucket.
# ---------------------------------------------------------------------------

def test_default_actor_id_falls_back_to_constant_when_no_model_id(tmp_path):
    audit = _SpyAuditClient()
    runner = TDDCycleRunner(ControlledPod(), audit_client=audit)
    runner.run(_spec(tmp_path))
    assert all(e["actor_id"] == "tdd-agent-cycle-runner" for e in audit.events)


def test_model_id_becomes_the_audit_actor_id(tmp_path):
    audit = _SpyAuditClient()
    runner = TDDCycleRunner(
        ControlledPod(), audit_client=audit, model_id="openrouter/deepseek/deepseek-v4",
    )
    runner.run(_spec(tmp_path))
    assert all(e["actor_id"] == "openrouter/deepseek/deepseek-v4" for e in audit.events)


def test_two_models_produce_distinct_actor_ids(tmp_path):
    """Regression: previously both would collapse to the same constant actor_id,
    so PerformanceAggregator.get_all_agent_metrics() could never see more than
    one 'agent' -- AdaptiveBroker had nothing to route between."""
    audit = _SpyAuditClient()
    TDDCycleRunner(ControlledPod(), audit_client=audit, model_id="model-a").run(_spec(tmp_path))
    TDDCycleRunner(ControlledPod(), audit_client=audit, model_id="model-b").run(_spec(tmp_path))

    actor_ids = {e["actor_id"] for e in audit.events}
    assert actor_ids == {"model-a", "model-b"}


def test_cycle_completed_payload_includes_elapsed_seconds_and_task_type(tmp_path):
    audit = _SpyAuditClient()
    runner = TDDCycleRunner(ControlledPod(), audit_client=audit, task_type="python")
    runner.run(_spec(tmp_path))

    from src.audit.schemas import AuditEventType
    completed = [e for e in audit.events if e["event_type"] == AuditEventType.CYCLE_COMPLETED]
    assert len(completed) == 1
    payload = completed[0]["payload"]
    assert payload["task_type"] == "python"
    assert isinstance(payload["elapsed_seconds"], float)
    assert payload["elapsed_seconds"] >= 0.0


def test_cycle_completed_never_fabricates_cost_or_quality_score(tmp_path):
    """No real pricing/quality-scoring instrument exists yet -- the payload
    must omit these keys rather than invent numbers AdaptiveBroker would
    silently route on."""
    audit = _SpyAuditClient()
    runner = TDDCycleRunner(ControlledPod(), audit_client=audit)
    runner.run(_spec(tmp_path))

    from src.audit.schemas import AuditEventType
    completed = [e for e in audit.events if e["event_type"] == AuditEventType.CYCLE_COMPLETED]
    payload = completed[0]["payload"]
    assert "cost" not in payload
    assert "quality_score" not in payload
    assert "complexity" not in payload


def test_performance_aggregator_distinguishes_models_after_real_cycles(tmp_path):
    """End-to-end regression: two different models' CYCLE_COMPLETED events,
    emitted through the real TDDCycleRunner, land as two separate agents in
    PerformanceAggregator -- the actual precondition AdaptiveBroker.route_task()
    needs to have more than one candidate to choose between."""
    from datetime import datetime, timezone

    from src.audit.schemas import AuditEvent, AuditEventType as _ET
    from src.broker.performance_aggregator import PerformanceAggregator

    class _RecordingAuditClient:
        def __init__(self):
            self.events = []

        def emit_simple(self, *, event_type, actor_id, payload, playbook_id=None):
            self.events.append(AuditEvent(
                event_id=f"e{len(self.events)}",
                event_type=event_type,
                actor_id=actor_id,
                actor_type="agent",
                timestamp=datetime.now(timezone.utc),
                payload=payload,
                prev_hash="0" * 64,
                playbook_id=playbook_id,
            ))

    class _StoreDouble:
        def __init__(self, client: _RecordingAuditClient):
            self._client = client

        def query(self, query):
            events = [e for e in self._client.events if e.event_type in query.event_types]
            if query.actor_id:
                events = [e for e in events if e.actor_id == query.actor_id]
            return type("Result", (), {"events": events})()

    audit = _RecordingAuditClient()
    TDDCycleRunner(ControlledPod(), audit_client=audit, model_id="model-a").run(_spec(tmp_path))
    TDDCycleRunner(ControlledPod(), audit_client=audit, model_id="model-b").run(_spec(tmp_path))

    aggregator = PerformanceAggregator(_StoreDouble(audit))
    all_metrics = aggregator.get_all_agent_metrics()

    assert set(all_metrics.keys()) == {"model-a", "model-b"}
    assert all_metrics["model-a"].total_tasks == 1
    assert all_metrics["model-b"].total_tasks == 1
