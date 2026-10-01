"""Tests for src/ui/broadcaster.py.

broadcast_event must never raise or meaningfully block a real build --
every test here is really asserting "this failure mode is swallowed."
"""
import json
import socket
import threading
from pathlib import Path
from unittest.mock import patch

import src.ui.broadcaster as broadcaster_module
from src.ui.broadcaster import (
    _MAX_PAYLOAD_BYTES,
    broadcast_event,
    current_phase,
    set_current_phase,
    set_project_root,
)
from src.ui.events import SandboxPostureEvent


def _event():
    return SandboxPostureEvent(
        pod_name="harness_test", network_mode="none", cap_drop="all",
        no_new_privileges=True, rootless=True, read_only_root=True,
    )


class TestNoOpWhenNoDashboard:
    def test_no_socket_file_is_a_silent_no_op(self, tmp_path):
        # No .ace/events.sock exists under tmp_path -- must not raise.
        broadcast_event(_event(), project_root=tmp_path)

    def test_no_socket_file_sends_nothing(self, tmp_path):
        with patch("socket.socket") as mock_socket_cls:
            broadcast_event(_event(), project_root=tmp_path)
        mock_socket_cls.assert_not_called()


class TestDeliveryWhenDashboardListening:
    def test_real_datagram_is_received_and_matches_the_event(self, tmp_path):
        sock_path = tmp_path / ".ace" / "events.sock"
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        server.bind(str(sock_path))
        server.settimeout(1.0)
        try:
            broadcast_event(_event(), project_root=tmp_path)
            data, _ = server.recvfrom(65536)
        finally:
            server.close()

        import json
        decoded = json.loads(data.decode("utf-8"))
        assert decoded["pod_name"] == "harness_test"
        assert decoded["type"] == "sandbox_posture"


class TestNeverRaises:
    def test_socket_creation_failure_is_swallowed(self, tmp_path):
        sock_path = tmp_path / ".ace" / "events.sock"
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        sock_path.touch()  # file exists so the no-op short-circuit is skipped

        with patch("socket.socket", side_effect=OSError("boom")):
            broadcast_event(_event(), project_root=tmp_path)  # must not raise

    def test_sendto_failure_is_swallowed(self, tmp_path):
        sock_path = tmp_path / ".ace" / "events.sock"
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        sock_path.touch()

        with patch.object(socket.socket, "sendto", side_effect=OSError("ECONNREFUSED")):
            broadcast_event(_event(), project_root=tmp_path)  # must not raise

    def test_unserializable_event_is_swallowed(self, tmp_path):
        sock_path = tmp_path / ".ace" / "events.sock"
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        sock_path.touch()

        class _NotADataclass:
            pass

        broadcast_event(_NotADataclass(), project_root=tmp_path)  # must not raise


class TestSettingsKillSwitch:
    def test_disabled_setting_prevents_any_socket_activity(self, tmp_path):
        sock_path = tmp_path / ".ace" / "events.sock"
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        sock_path.touch()

        with patch("src.config.settings.settings.enable_event_broadcasting", False), \
             patch("socket.socket") as mock_socket_cls:
            broadcast_event(_event(), project_root=tmp_path)
        mock_socket_cls.assert_not_called()


class TestPayloadSizeGuard:
    def test_oversized_payload_is_dropped_not_sent(self, tmp_path):
        sock_path = tmp_path / ".ace" / "events.sock"
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        sock_path.touch()

        huge_event = SandboxPostureEvent(
            pod_name="x", network_mode="none", cap_drop="all",
            no_new_privileges=True, rootless=True, read_only_root=True,
            ro_mounts=["x" * _MAX_PAYLOAD_BYTES],
        )
        with patch("socket.socket") as mock_socket_cls:
            broadcast_event(huge_event, project_root=tmp_path)
        mock_socket_cls.assert_not_called()


class TestProjectRootDefaulting:
    """Regression: every instrumentation call site (PodmanRunner.start(),
    TDDCycleRunner, AuditStore.append()) calls broadcast_event(event) with
    NO project_root -- found live, running the real dashboard against a
    real build whose --project differed from the calling process's CWD,
    where events silently went to the wrong (nonexistent) socket path and
    never reached the dashboard. set_project_root() is what the CLI entry
    points call once, so every such call site picks up the real target."""

    def setup_method(self):
        # Module-level global -- other tests in this same process (anything
        # exercising cmd_tdd/cmd_project for real, not mocking
        # set_project_root) legitimately call the real set_project_root(),
        # by design. Force a known, controlled starting state here rather
        # than assuming "never called yet" -- that assumption is only true
        # in isolation, not across the whole suite, and test order isn't
        # something to depend on.
        self._original_root = broadcaster_module._current_project_root
        broadcaster_module._current_project_root = Path(".")

    def teardown_method(self):
        # Must not leak this test's project_root into any other test that
        # calls broadcast_event() without one.
        broadcaster_module._current_project_root = self._original_root

    def test_fresh_state_with_set_project_root_never_called_defaults_to_cwd(self):
        assert broadcaster_module._current_project_root == Path(".")

    def test_set_project_root_changes_the_default_broadcast_target(self, tmp_path):
        sock_path = tmp_path / ".ace" / "events.sock"
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        server.bind(str(sock_path))
        server.settimeout(1.0)
        try:
            set_project_root(tmp_path)
            broadcast_event(_event())  # no project_root passed -- the real instrumentation shape
            data, _ = server.recvfrom(65536)
        finally:
            server.close()
        assert json.loads(data.decode("utf-8"))["pod_name"] == "harness_test"

    def test_explicit_project_root_still_overrides_the_global_default(self, tmp_path):
        other_dir = tmp_path / "other"
        real_dir = tmp_path / "real"
        for d in (other_dir, real_dir):
            (d / ".ace").mkdir(parents=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        server.bind(str(real_dir / ".ace" / "events.sock"))
        server.settimeout(1.0)
        try:
            set_project_root(other_dir)  # global points elsewhere
            broadcast_event(_event(), project_root=real_dir)  # explicit arg wins
            data, _ = server.recvfrom(65536)
        finally:
            server.close()
        assert json.loads(data.decode("utf-8"))["pod_name"] == "harness_test"

    def test_wrong_cwd_with_no_set_project_root_reproduces_the_original_bug(self, tmp_path):
        # The exact failure mode found live: a socket exists at the real
        # project root, but nothing ever calls set_project_root(), so the
        # event (correctly, per the OLD default) goes to "." instead and is
        # never seen -- pinning this down as the documented pre-fix
        # behavior, not a surprise regression.
        real_dir = tmp_path / "real"
        (real_dir / ".ace").mkdir(parents=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        server.bind(str(real_dir / ".ace" / "events.sock"))
        server.settimeout(0.3)
        try:
            broadcast_event(_event())  # no set_project_root(), no explicit arg
            raised = False
            try:
                server.recvfrom(65536)
            except TimeoutError:
                raised = True
            assert raised, "event should NOT have reached a socket it was never told about"
        finally:
            server.close()


class TestPhaseContext:
    """current_phase() backs issue #77's incremental "chunk" streaming --
    unlike _current_project_root, this MUST be thread-local: src/ensemble/
    learner.py runs multiple TDDCycleRunners concurrently via
    ThreadPoolExecutor, so a plain global would let one model's GREEN phase
    clobber another's in-flight RED tag."""

    def setup_method(self):
        set_current_phase(None)

    def teardown_method(self):
        set_current_phase(None)

    def test_defaults_to_none(self):
        assert current_phase() is None

    def test_set_then_get_on_the_same_thread(self):
        set_current_phase("GREEN")
        assert current_phase() == "GREEN"

    def test_reset_to_none(self):
        set_current_phase("RED")
        set_current_phase(None)
        assert current_phase() is None

    def test_concurrent_threads_do_not_see_each_others_phase(self):
        observed: dict[str, str | None] = {}
        barrier = threading.Barrier(2)

        def worker(name: str, phase: str) -> None:
            set_current_phase(phase)
            barrier.wait(timeout=5)  # force both threads to have set their phase before either reads
            observed[name] = current_phase()

        t1 = threading.Thread(target=worker, args=("a", "RED"))
        t2 = threading.Thread(target=worker, args=("b", "GREEN"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert observed == {"a": "RED", "b": "GREEN"}
