"""`ace dashboard` -- a real-time mission-control Textual TUI.

Listens on `.ace/events.sock` (the same socket `src/ui/broadcaster.py`
sends to) and renders the four event types from `src/ui/events.py` live:
sandbox posture, phase execution stream, playbook deltas, and the audit
hash chain. Entirely decoupled from the build it observes -- a crash or
hang in this file can never affect a real `ace tdd`/`ace project` run,
since broadcasting is fire-and-forget and this process is either a
separate sidecar or, for `--watch`, a background thread whose only
interaction with the build is receiving its own broadcast events.

`textual` is an optional dependency (`pip install -e .[dashboard]`) --
nothing in `src/ui/events.py`/`broadcaster.py` needs it; only this module
and `cmd_dashboard` (`src/cli/main.py`) import it, and only when a dashboard
is actually requested.
"""
from __future__ import annotations

import json
import logging
import socket
from collections.abc import Callable
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import DataTable, Footer, Header, RichLog, Static

logger = logging.getLogger(__name__)

_SOCKET_RELPATH = ".ace/events.sock"
_MAX_AUDIT_TICKER_ROWS = 20


class PostureBar(Static):
    """Top bar -- the most recently broadcast SandboxPostureEvent, rendered
    as explicit pass/fail indicators. Starts in a "waiting" state since a
    container may not have started yet when the dashboard first connects."""

    def on_mount(self) -> None:
        self.update("[dim]Sandbox posture: waiting for a container to start...[/]")

    def update_posture(self, payload: dict) -> None:
        network = "[green]Blocked[/]" if payload.get("network_mode") == "none" else "[red]OPEN[/]"
        caps = "[green]Dropped[/]" if payload.get("cap_drop") == "all" else "[red]RETAINED[/]"
        privs = "[green]Locked[/]" if payload.get("no_new_privileges") else "[red]UNLOCKED[/]"
        rootless = "[green]True[/]" if payload.get("rootless") else "[red]False[/]"
        ro_root = "[green]True[/]" if payload.get("read_only_root") else "[red]False[/]"
        pod_name = payload.get("pod_name", "?")
        self.update(
            f"[b]{pod_name}[/]  "
            f"Network Egress: {network}  |  Caps: {caps}  |  "
            f"Privileges: {privs}  |  Rootless: {rootless}  |  RO Root: {ro_root}"
        )


class AuditTicker(Static):
    """Bottom bar -- last N AuditChainEvent hashes, newest first."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._hashes: list[str] = []

    def on_mount(self) -> None:
        self.update("[dim]Audit chain: no events yet[/]")

    def add_hash(self, event_type: str, event_hash: str) -> None:
        self._hashes.insert(0, f"[cyan]{event_type}[/] {event_hash[:12]}")
        self._hashes = self._hashes[:_MAX_AUDIT_TICKER_ROWS]
        self.update(" → ".join(self._hashes))


class DashboardApp(App):
    """Mission-control TUI. `build_fn`, when given (the `ace tdd --watch`
    case), is run as a background worker thread from `on_mount` -- this
    app owns the terminal (its own `run()` call), the build never spawns a
    second process to fight it for the TTY."""

    TITLE = "ACE Mission Control"

    CSS = """
    Screen {
        background: #1a1b26;
        color: #c0caf5;
    }
    #posture {
        height: 3;
        background: #24283b;
        color: #9ece6a;
        content-align: center middle;
        border-bottom: solid #414868;
    }
    #body {
        height: 1fr;
    }
    #exec_log {
        width: 65%;
        border: solid #414868;
        background: #1a1b26;
    }
    #playbook_table {
        width: 35%;
        border: solid #414868;
        background: #1a1b26;
    }
    #audit_ticker {
        height: 3;
        background: #24283b;
        color: #e0af68;
        content-align: left middle;
        border-top: solid #414868;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("c", "clear_log", "Clear log"),
    ]

    def __init__(self, project_root: str | Path = ".", build_fn: Callable[[], int] | None = None) -> None:
        super().__init__()
        self._project_root = Path(project_root)
        self._build_fn = build_fn
        self._sock: socket.socket | None = None
        self.build_exit_code: int | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield PostureBar(id="posture")
        with Horizontal(id="body"):
            yield RichLog(id="exec_log", auto_scroll=True, wrap=True, markup=True)
            yield DataTable(id="playbook_table")
        yield AuditTicker(id="audit_ticker")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#playbook_table", DataTable)
        table.add_columns("Cycle", "Section", "Bullet", "Root Cause")
        self._start_socket_listener()
        if self._build_fn is not None:
            self.run_worker(self._run_build, thread=True, exit_on_error=False)

    def on_unmount(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        sock_path = self._project_root / _SOCKET_RELPATH
        sock_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Socket listener (background thread -> call_from_thread into the UI)
    # ------------------------------------------------------------------

    def _start_socket_listener(self) -> None:
        sock_path = self._project_root / _SOCKET_RELPATH
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        # Stale socket file from a crashed prior run -- bind() fails on an
        # existing path regardless of whether anything is still listening.
        sock_path.unlink(missing_ok=True)

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._sock.bind(str(sock_path))
        self._sock.settimeout(0.2)
        self.run_worker(self._listen_loop, thread=True, exclusive=True, group="event_listener")

    def _listen_loop(self) -> None:
        assert self._sock is not None
        while True:
            try:
                data, _addr = self._sock.recvfrom(65536)
            except TimeoutError:
                continue
            except OSError:
                # Socket closed (on_unmount) -- the listener's own cue to stop.
                return
            try:
                payload = json.loads(data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.debug("dashboard: dropped malformed event payload", exc_info=True)
                continue
            self.call_from_thread(self._handle_event, payload)

    def _handle_event(self, payload: dict) -> None:
        event_type = payload.get("type")
        try:
            if event_type == "sandbox_posture":
                self.query_one(PostureBar).update_posture(payload)
            elif event_type == "execution_stream":
                self._append_execution_log(payload)
            elif event_type == "playbook_delta":
                self._append_playbook_row(payload)
            elif event_type == "audit_chain":
                self.query_one(AuditTicker).add_hash(payload.get("event_type", "?"), payload.get("event_hash", ""))
        except Exception:
            # A malformed/unexpected payload must never crash the dashboard.
            logger.debug("dashboard: failed to render event %r", event_type, exc_info=True)

    def _append_execution_log(self, payload: dict) -> None:
        log = self.query_one("#exec_log", RichLog)
        phase = payload.get("phase", "?")
        status = payload.get("status")
        if status == "started":
            log.write(f"[b]── {phase} ──[/]")
        elif status == "chunk":
            # One real-time line of subprocess output (issue #77) -- no
            # phase/exit_code label here, that belongs to the one
            # "completed" event per phase below, not every line in between.
            chunk = payload.get("stdout_chunk") or ""
            if chunk:
                log.write(chunk)
        else:
            chunk = payload.get("stdout_chunk") or ""
            if chunk:
                log.write(chunk)
            exit_code = payload.get("exit_code")
            color = "green" if exit_code == 0 else "red"
            log.write(f"[{color}]{phase} completed (exit_code={exit_code})[/]")

    def _append_playbook_row(self, payload: dict) -> None:
        table = self.query_one("#playbook_table", DataTable)
        table.add_row(
            str(payload.get("cycle_number", "?")),
            payload.get("bullet_section", ""),
            payload.get("bullet_content", ""),
            payload.get("root_cause", ""),
        )

    # ------------------------------------------------------------------
    # --watch: the build runs as a background worker in this same process
    # ------------------------------------------------------------------

    def _run_build(self) -> None:
        try:
            self.build_exit_code = self._build_fn()
        except Exception as exc:
            self.build_exit_code = 1
            self.call_from_thread(self.notify, f"Build crashed: {exc}", severity="error", timeout=10)
        self.call_from_thread(self._on_build_complete)

    def _on_build_complete(self) -> None:
        self.title = f"ACE Mission Control — build complete (exit {self.build_exit_code})"
        self.notify("Build complete -- review the panels, press q to quit.", timeout=10)

    # ------------------------------------------------------------------
    # Keybindings
    # ------------------------------------------------------------------

    def action_clear_log(self) -> None:
        self.query_one("#exec_log", RichLog).clear()


def run_dashboard(project_root: str | Path = ".") -> int:
    """Standalone `ace dashboard` -- just listens and renders."""
    app = DashboardApp(project_root=project_root)
    app.run()
    return 0


def run_dashboard_with_worker(build_fn: Callable[[], int], project_root: str | Path = ".") -> int:
    """`ace tdd --watch` -- this app owns the terminal; `build_fn` (the
    normal `ace tdd` build logic) runs as a background worker thread in
    this same process, so its broadcast_event() calls reach this app's own
    socket listener exactly like a separate `ace dashboard` process would
    receive them from a separate `ace tdd` process."""
    app = DashboardApp(project_root=project_root, build_fn=build_fn)
    app.run()
    return app.build_exit_code if app.build_exit_code is not None else 1
