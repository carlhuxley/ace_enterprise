"""Event schemas for the live mission-control dashboard (`ace dashboard`).

Broadcast fire-and-forget over a UNIX DGRAM socket (`.ace/events.sock`) by
`src/ui/broadcaster.py`; consumed by the Textual TUI in `src/ui/dashboard.py`.
Every event is a flat, JSON-serializable dataclass -- no behavior, just
data, so broadcasting can never meaningfully couple the dashboard to ACE's
core execution logic (a bug in event construction/serialization must never
affect a real build; see `broadcaster.py`'s own try/except-everything
design).

Field names are deliberately tied to real attributes elsewhere in the
codebase, not invented metrics -- e.g. `PlaybookDeltaEvent.root_cause`
mirrors `storage.schemas.ReflectorOutput.root_cause` verbatim, and there is
no `cgr3_score` field here: CGR3 (`src/retrieval/cgr3_retriever.py`) is a
separate, retrieval-time subsystem never reached by the TDD learn loop
these events are broadcast from.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

# Kept well under common UNIX SOCK_DGRAM kernel buffer limits even after
# JSON overhead (field names, quoting) is added on top -- broadcaster.py's
# own hard ceiling (checked against the final serialized payload) is the
# real last line of defense; this is what keeps stdout_chunk from needing
# that fallback in the first place for the overwhelmingly common case.
_MAX_OUTPUT_BYTES = 32_768
_MAX_OUTPUT_LINES = 500


def _truncate_output(text: str, max_bytes: int = _MAX_OUTPUT_BYTES, max_lines: int = _MAX_OUTPUT_LINES) -> str:
    """Keep the LAST `max_lines` lines of `text`, further capped to the
    last `max_bytes` -- a failing assertion/traceback is almost always at
    the end of pytest/vitest/go test output, not the setup noise, so
    truncating from the front preserves the actionable part. A leading
    marker is added only when truncation actually happened, so a short
    chunk round-trips byte-for-byte unchanged."""
    if not text:
        return text

    lines = text.splitlines()
    truncated_lines = len(lines) > max_lines
    if truncated_lines:
        kept_lines = lines[-max_lines:]
    else:
        kept_lines = lines
    result = "\n".join(kept_lines)

    encoded = result.encode("utf-8", errors="replace")
    truncated_bytes = len(encoded) > max_bytes
    if truncated_bytes:
        result = encoded[-max_bytes:].decode("utf-8", errors="ignore")

    if not (truncated_lines or truncated_bytes):
        return text

    total_lines = len(lines)
    shown_lines = len(result.splitlines())
    return f"...[truncated: showing last {shown_lines} of {total_lines} lines]\n{result}"


@dataclass
class SandboxPostureEvent:
    """Real, read-back zero-trust posture of a just-started Podman sandbox
    container -- every field reports an actual flag `PodmanRunner.start()`
    (`src/agents/podman_runner.py`) passed to `podman run`, never inferred
    or assumed. Fired once per container start, not once per pulse."""

    pod_name: str
    network_mode: str  # "none"
    cap_drop: str  # "all"
    no_new_privileges: bool
    rootless: bool  # achieved by how podman is invoked (host's own non-root user), not a discrete flag
    read_only_root: bool
    ro_mounts: list[str] = field(default_factory=list)
    active_phase: str | None = None
    timestamp: float = field(default_factory=time.time)
    type: str = "sandbox_posture"


@dataclass
class ExecutionStreamEvent:
    """One phase's test-runner/oracle output. "started"/"completed" mark the
    phase boundary (the latter carrying the full captured output); "chunk"
    is one line of real-time stdout/stderr from the underlying subprocess,
    broadcast by src/agents/podman_runner.py's `_run_streaming()` helper as
    pytest/go test/vitest/bandit/gosec/eslint/errcheck/revive actually
    produce it (gofmt is the one exception -- its stdout is reformatted
    source code, not log output, so it stays a plain blocking call and
    never emits "chunk" events)."""

    phase: str  # "RED" | "GREEN" | "REFACTOR"
    status: str  # "started" | "chunk" | "completed"
    cycle_number: int = 0
    stdout_chunk: str = ""
    exit_code: int | None = None
    timestamp: float = field(default_factory=time.time)
    type: str = "execution_stream"

    def __post_init__(self) -> None:
        self.stdout_chunk = _truncate_output(self.stdout_chunk)


@dataclass
class PlaybookDeltaEvent:
    """One Curator delta bullet written during `TDDCycleRunner._learn()`.
    Field names match `DeltaBullet`/`ReflectorOutput`'s real attributes
    (`src/storage/schemas.py`) -- no `cgr3_score`: CGR3 is a separate
    retrieval-time subsystem, not reachable from the learn loop this event
    is broadcast from."""

    bullet_content: str
    bullet_section: str
    root_cause: str
    cycle_number: int
    timestamp: float = field(default_factory=time.time)
    type: str = "playbook_delta"


@dataclass
class AuditChainEvent:
    """Mirrors one just-appended `AuditEvent`'s real hash-chain fields
    (`src/audit/schemas.py`). `event_type` is the real `AuditEventType`
    enum value's string -- there is no generic "stage_name" field on
    `AuditEvent`."""

    event_type: str
    event_hash: str
    prev_hash: str | None
    timestamp: float = field(default_factory=time.time)
    type: str = "audit_chain"
