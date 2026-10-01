"""Fire-and-forget UDP/DGRAM broadcaster for live dashboard events.

Zero-overhead no-op when `.ace/events.sock` doesn't exist (no `ace
dashboard` listening) -- every call is wrapped so a broadcasting failure
can NEVER affect a real build. One well-known socket path per project
root, one sender (the running ACE process), one reader in practice (the
dashboard TUI), though nothing here assumes exactly one.
"""
from __future__ import annotations

import json
import logging
import socket
from dataclasses import asdict
from pathlib import Path

logger = logging.getLogger(__name__)

_SOCKET_RELPATH = ".ace/events.sock"

# Instrumentation call sites (PodmanRunner, TDDCycleRunner, AuditStore) have
# no project-root concept of their own to thread through -- broadcasting is
# a cross-cutting observability concern, not a per-object dependency. The
# CLI entry points (cmd_tdd/_run_tdd_build, cmd_project, cmd_dashboard) call
# set_project_root() exactly once, right after resolving --project, so
# every broadcast_event() call anywhere in the process picks up the right
# target without every class needing its own project_root parameter.
# Defaults to "." (today's behavior) when never set -- correct for the
# common case of running `ace` from inside the project directory, same as
# every call site's own prior default.
_current_project_root: Path = Path(".")


def set_project_root(project_root: Path | str) -> None:
    """Set the project root every subsequent broadcast_event() call in this
    process defaults to, unless it passes its own project_root explicitly."""
    global _current_project_root
    _current_project_root = Path(project_root)

# Comfortably under common UNIX SOCK_DGRAM kernel buffer limits (commonly
# ~64KB default, platform/sysctl-dependent) even after JSON framing
# overhead -- the real last line of defense against EMSGSIZE, generic
# (keyed off the whole serialized payload) so a future event type can't
# reintroduce the risk by adding a large field events.py's own
# per-field truncation (e.g. ExecutionStreamEvent.stdout_chunk) doesn't
# know about.
_MAX_PAYLOAD_BYTES = 56 * 1024


def _socket_path(project_root: Path | str = ".") -> Path:
    return Path(project_root) / _SOCKET_RELPATH


def broadcast_event(event, project_root: Path | str | None = None) -> None:
    """Send `event` (any dataclass from `src/ui/events.py`) to the
    dashboard socket if one is listening. Does nothing otherwise -- this
    must never raise, meaningfully block, or slow down a real build.

    `project_root` defaults to whatever `set_project_root()` was last
    called with in this process (or "." if never called) -- pass it
    explicitly only when broadcasting for a project other than the one the
    current CLI invocation is building (e.g. tests)."""
    try:
        from src.config.settings import settings

        if not settings.enable_event_broadcasting:
            return
    except Exception:
        # Settings import/construction failing is not this function's
        # problem to surface -- fail open to "try to broadcast" rather
        # than silently disabling observability over an unrelated config
        # error, but never let it propagate.
        pass

    path = _socket_path(project_root if project_root is not None else _current_project_root)
    if not path.exists():
        return

    try:
        payload = json.dumps(asdict(event)).encode("utf-8")
    except Exception:
        logger.debug("broadcaster: event not JSON-serializable", exc_info=True)
        return

    if len(payload) > _MAX_PAYLOAD_BYTES:
        logger.debug(
            "broadcaster: dropping oversized event (%d bytes > %d limit)",
            len(payload), _MAX_PAYLOAD_BYTES,
        )
        return

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.05)
            sock.sendto(payload, str(path))
    except OSError:
        # No listener, stale socket file, permissions, EMSGSIZE despite
        # the size guard above (e.g. a stricter platform limit) -- none of
        # these are a build's problem.
        logger.debug("broadcaster: event not delivered", exc_info=True)
    except Exception:
        logger.debug("broadcaster: unexpected error broadcasting event", exc_info=True)
