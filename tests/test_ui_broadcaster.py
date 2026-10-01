"""Tests for src/ui/broadcaster.py.

broadcast_event must never raise or meaningfully block a real build --
every test here is really asserting "this failure mode is swallowed."
"""
import socket
from unittest.mock import patch

from src.ui.broadcaster import _MAX_PAYLOAD_BYTES, broadcast_event
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
