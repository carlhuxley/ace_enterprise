"""Tests for src/broker/model_router.py -- the live AdaptiveBroker entry point.

route_model() is what `ace tdd` (via factory.build_agent) and the MCP
build_feature tool call to pick which configured model runs a build. These
tests drive it against an in-memory audit store, never a real LLM.
"""
import uuid
from datetime import UTC, datetime

import pytest

from src.audit.schemas import AuditEvent, AuditEventType
from src.audit.store import AuditStore
from src.broker.model_router import ModelRoutingDecision, route_model


def _store_with_cycles(url: str, rows: list[tuple[str, str, bool, float]]) -> None:
    """rows: (actor_id, task_type, success, elapsed_seconds)."""
    store = AuditStore(url)
    store.create_tables()
    for actor_id, task_type, success, elapsed in rows:
        store.append(
            AuditEvent(
                event_id=str(uuid.uuid4()),
                event_type=AuditEventType.CYCLE_COMPLETED,
                timestamp=datetime.now(UTC),
                actor_type="agent",
                actor_id=actor_id,
                payload={"success": success, "elapsed_seconds": elapsed, "task_type": task_type},
            )
        )


@pytest.fixture
def audit_url(tmp_path):
    return f"sqlite:///{tmp_path / 'audit.db'}"


@pytest.fixture(autouse=True)
def _no_real_calibration(monkeypatch):
    """Cold-start calibration (#5) spins up a real sandboxed TDD cycle by
    default. Every test in this file except TestColdStartCalibration below
    must stay hermetic -- stub it to a no-op so existing fallback/no-history
    behavior is exercised exactly as before calibration was added."""
    monkeypatch.setattr(
        "src.broker.calibration.calibrate_cold_start_models", lambda *a, **k: None
    )


def test_single_candidate_is_a_noop_route(audit_url):
    decision = route_model(["ollama/qwen2.5-coder:7b"], "python", audit_url)
    assert decision.selected_model == "ollama/qwen2.5-coder:7b"
    assert decision.is_fallback is True
    assert decision.verdict == "SKIP"
    assert "single candidate" in decision.reason


def test_empty_candidates_raises():
    with pytest.raises(ValueError, match="at least one candidate"):
        route_model([], "python", "sqlite:///:memory:")


def test_no_history_falls_back_to_first_candidate(audit_url):
    decision = route_model(
        ["openrouter/deepseek/deepseek-v3", "ollama/qwen2.5-coder:7b"],
        "python",
        audit_url,
    )
    assert decision.is_fallback is True
    assert decision.selected_model == "openrouter/deepseek/deepseek-v3"
    assert decision.candidates == [
        "openrouter/deepseek/deepseek-v3",
        "ollama/qwen2.5-coder:7b",
    ]


def test_routes_to_the_candidate_with_the_better_history(audit_url):
    _store_with_cycles(
        audit_url,
        [("provA/m", "python", True, 5.0)] * 18
        + [("provB/m", "python", False, 5.0)] * 15
        + [("provB/m", "python", True, 5.0)] * 3,
    )
    decision = route_model(["provA/m", "provB/m"], "python", audit_url)
    assert decision.is_fallback is False
    assert decision.selected_model == "provA/m"
    assert decision.confidence > 0.0
    assert {ref for ref, _ in decision.scored_candidates} == {"provA/m", "provB/m"}


def test_allowed_agents_filter_excludes_non_candidates(audit_url):
    # A third, strong model exists in history but isn't a candidate -> ignored.
    _store_with_cycles(
        audit_url,
        [("provC/strong", "python", True, 1.0)] * 30
        + [("provA/m", "python", True, 5.0)] * 18
        + [("provB/m", "python", False, 5.0)] * 18,
    )
    decision = route_model(["provA/m", "provB/m"], "python", audit_url)
    assert decision.selected_model == "provA/m"
    assert "provC/strong" not in dict(decision.scored_candidates)


def test_broker_error_degrades_to_fallback_not_exception():
    decision = route_model(
        ["provA/m", "provB/m"], "python", "sqlite:////nonexistent/dir/audit.db"
    )
    assert decision.is_fallback is True
    assert decision.selected_model == "provA/m"
    assert "routing error" in decision.reason or "no audit history" in decision.reason


def test_to_payload_is_json_safe(audit_url):
    import json

    decision = route_model(["provA/m", "provB/m"], "python", audit_url)
    json.dumps(decision.to_payload())  # must not raise


def test_summary_line_shapes():
    fb = ModelRoutingDecision("a/m", ["a/m", "b/m"], 0.0, "ASK_FIRST", True)
    assert "fallback" in fb.summary_line()
    ranked = ModelRoutingDecision(
        "a/m", ["a/m", "b/m"], 0.82, "APPLY", False,
        scored_candidates=[("a/m", 0.82), ("b/m", 0.40)],
    )
    assert "APPLY" in ranked.summary_line()
    assert "b/m=0.40" in ranked.summary_line()


# ---------------------------------------------------------------------------
# Cold-start calibration (#5) -- these override the module's autouse stub.
# ---------------------------------------------------------------------------

class TestColdStartCalibration:
    def test_calibration_is_called_only_for_candidates_with_no_history(self, audit_url, monkeypatch):
        _store_with_cycles(audit_url, [("provA/m", "python", True, 5.0)] * 5)
        calls = []
        monkeypatch.setattr(
            "src.broker.calibration.calibrate_cold_start_models",
            lambda refs, url, **kw: calls.append(list(refs)),
        )

        route_model(["provA/m", "provB/cold"], "python", audit_url)

        assert calls == [["provB/cold"]]

    def test_both_candidates_cold_calibrates_both(self, audit_url, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "src.broker.calibration.calibrate_cold_start_models",
            lambda refs, url, **kw: calls.append(list(refs)),
        )

        route_model(["provA/cold", "provB/cold"], "python", audit_url)

        assert calls and set(calls[0]) == {"provA/cold", "provB/cold"}

    def test_freshly_calibrated_model_is_routable_on_the_same_call(self, audit_url, monkeypatch):
        # The stubbed calibration writes a real audit event, same shape a
        # real calibration cycle's CYCLE_COMPLETED emission would produce --
        # proves the aggregator rebuild after calibration isn't stale.
        def fake_calibrate(refs, url, **kw):
            _store_with_cycles(url, [(refs[0], "python", True, 1.0)] * 10)

        monkeypatch.setattr(
            "src.broker.calibration.calibrate_cold_start_models", fake_calibrate
        )
        _store_with_cycles(audit_url, [("provA/m", "python", False, 5.0)] * 10)

        decision = route_model(["provA/m", "provB/cold"], "python", audit_url)

        assert decision.is_fallback is False
        assert decision.selected_model == "provB/cold"

    def test_calibration_disabled_skips_it_entirely(self, audit_url, monkeypatch):
        called = []
        monkeypatch.setattr(
            "src.broker.calibration.calibrate_cold_start_models",
            lambda *a, **k: called.append(True),
        )

        decision = route_model(
            ["provA/cold", "provB/cold"], "python", audit_url, calibrate_cold_start=False,
        )

        assert called == []
        assert decision.is_fallback is True

    def test_calibration_raising_does_not_block_routing(self, audit_url, monkeypatch):
        def fake_calibrate(refs, url, **kw):
            raise RuntimeError("sandbox unavailable")

        monkeypatch.setattr(
            "src.broker.calibration.calibrate_cold_start_models", fake_calibrate
        )

        decision = route_model(["provA/cold", "provB/cold"], "python", audit_url)

        assert decision.is_fallback is True
        assert decision.selected_model == "provA/cold"
