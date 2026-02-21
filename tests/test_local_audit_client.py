"""Tests for local audit client."""
import pytest
import tempfile
from pathlib import Path


class TestLocalAuditClient:
    """Tests for LocalAuditClient."""

    def test_emit_event(self):
        """Should store event in local SQLite database."""
        from src.audit.local_client import LocalAuditClient
        from src.audit.schemas import AuditEventType

        # Use temp database
        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{tmpdir}/audit.db"
            client = LocalAuditClient(db_url)

            result = client.emit_simple(
                AuditEventType.PATTERN_LEARNED,
                actor_id="test-agent",
                payload={"pattern_id": "ctx-001"}
            )

            assert result is True
            stats = client.get_stats()
            assert stats["total_events"] == 1

    def test_emit_multiple_events(self):
        """Should store multiple events with hash chain."""
        from src.audit.local_client import LocalAuditClient
        from src.audit.schemas import AuditEventType

        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{tmpdir}/audit.db"
            client = LocalAuditClient(db_url)

            client.emit_simple(AuditEventType.TEST_GENERATED, "agent-1")
            client.emit_simple(AuditEventType.IMPLEMENTATION_GENERATED, "agent-1")
            client.emit_simple(AuditEventType.CYCLE_COMPLETED, "agent-1")

            stats = client.get_stats()
            assert stats["total_events"] == 3

    def test_events_by_type(self):
        """Should track event counts by type."""
        from src.audit.local_client import LocalAuditClient
        from src.audit.schemas import AuditEventType

        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{tmpdir}/audit.db"
            client = LocalAuditClient(db_url)

            client.emit_simple(AuditEventType.TEST_GENERATED, "agent-1")
            client.emit_simple(AuditEventType.TEST_GENERATED, "agent-1")
            client.emit_simple(AuditEventType.CYCLE_COMPLETED, "agent-1")

            stats = client.get_stats()
            assert stats["events_by_type"][AuditEventType.TEST_GENERATED] == 2
            assert stats["events_by_type"][AuditEventType.CYCLE_COMPLETED] == 1

    def test_context_manager(self):
        """Should work as context manager."""
        from src.audit.local_client import LocalAuditClient
        from src.audit.schemas import AuditEventType

        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{tmpdir}/audit.db"

            with LocalAuditClient(db_url) as client:
                client.emit_simple(AuditEventType.AGENT_STARTED, "test-agent")
                stats = client.get_stats()
                assert stats["total_events"] == 1


class TestGetLocalAuditClient:
    """Tests for get_local_audit_client factory."""

    def test_creates_client_with_default_path(self):
        """Should create client with default database path."""
        from src.audit.local_client import get_local_audit_client

        client = get_local_audit_client()
        assert client is not None
        assert ".local/audit.db" in client._database_url

    def test_creates_client_with_custom_path(self):
        """Should create client with custom database path."""
        from src.audit.local_client import get_local_audit_client

        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{tmpdir}/custom.db"
            client = get_local_audit_client(db_url)
            assert client._database_url == db_url
