"""Tests for src/ui/events.py."""
import json
from dataclasses import asdict

from src.ui.events import (
    AuditChainEvent,
    ExecutionStreamEvent,
    PlaybookDeltaEvent,
    SandboxPostureEvent,
    _truncate_output,
)


class TestEventsJsonRoundTrip:
    def test_sandbox_posture_event_round_trips(self):
        event = SandboxPostureEvent(
            pod_name="harness_abc123", network_mode="none", cap_drop="all",
            no_new_privileges=True, rootless=True, read_only_root=True,
            ro_mounts=["/tmp/ace_ws_abc123"],
        )
        decoded = json.loads(json.dumps(asdict(event)))
        assert decoded["pod_name"] == "harness_abc123"
        assert decoded["type"] == "sandbox_posture"
        assert decoded["ro_mounts"] == ["/tmp/ace_ws_abc123"]

    def test_execution_stream_event_round_trips(self):
        event = ExecutionStreamEvent(phase="GREEN", status="completed", stdout_chunk="1 passed", exit_code=0)
        decoded = json.loads(json.dumps(asdict(event)))
        assert decoded["phase"] == "GREEN"
        assert decoded["status"] == "completed"
        assert decoded["exit_code"] == 0
        assert decoded["type"] == "execution_stream"

    def test_playbook_delta_event_round_trips(self):
        event = PlaybookDeltaEvent(
            bullet_content="always validate inputs", bullet_section="strategies_and_hard_rules",
            root_cause="missing boundary check", cycle_number=3,
        )
        decoded = json.loads(json.dumps(asdict(event)))
        assert decoded["bullet_content"] == "always validate inputs"
        assert decoded["cycle_number"] == 3
        assert decoded["type"] == "playbook_delta"
        assert "cgr3_score" not in decoded

    def test_audit_chain_event_round_trips(self):
        event = AuditChainEvent(event_type="CYCLE_COMPLETED", event_hash="abc123", prev_hash="def456")
        decoded = json.loads(json.dumps(asdict(event)))
        assert decoded["event_type"] == "CYCLE_COMPLETED"
        assert decoded["event_hash"] == "abc123"
        assert decoded["type"] == "audit_chain"


class TestTruncateOutput:
    def test_short_text_passes_through_unchanged(self):
        assert _truncate_output("1 passed in 0.01s") == "1 passed in 0.01s"

    def test_empty_text_passes_through(self):
        assert _truncate_output("") == ""

    def test_truncates_to_last_n_lines(self):
        lines = [f"line {i}" for i in range(1000)]
        text = "\n".join(lines)
        result = _truncate_output(text, max_lines=10, max_bytes=1_000_000)
        assert "line 999" in result
        assert "line 0\n" not in result
        assert "truncated" in result
        assert result.count("\n") <= 10  # marker line + 10 kept lines

    def test_truncates_to_last_n_bytes(self):
        text = "x" * 100_000
        result = _truncate_output(text, max_lines=1_000_000, max_bytes=100)
        assert len(result.encode("utf-8")) < 200  # kept portion + marker text
        assert "truncated" in result

    def test_execution_stream_event_auto_truncates_stdout_chunk(self):
        huge = "\n".join(f"line {i}" for i in range(1000))
        event = ExecutionStreamEvent(phase="RED", status="completed", stdout_chunk=huge)
        assert "truncated" in event.stdout_chunk
        assert len(event.stdout_chunk.splitlines()) <= 501  # marker + 500 lines
