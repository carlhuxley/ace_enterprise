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


class TestVerifyFullChainAgainstSQLiteRoundTrip:
    """Regression: SQLite's DateTime(timezone=True) column does not actually
    preserve tzinfo on read-back -- a timezone-aware datetime.now(UTC)
    (what LocalAuditClient.emit() stamps every event with) round-trips as
    naive. AuditEvent.compute_hash() used to hash str(timestamp) directly,
    so the same event hashed a different way at write time vs at
    verify_full_chain()'s read-time reconstruction -- a false-positive
    "tampered" result on data nobody touched. Uses a real file-backed
    SQLite DB (not :memory:) since that's what actually exhibits the
    round-trip, and a *separate* AuditStore instance for verification to
    match how an independent auditor would actually check the chain.
    """

    def test_two_events_verify_clean_on_file_backed_sqlite(self):
        from src.audit.local_client import LocalAuditClient
        from src.audit.schemas import AuditEventType
        from src.audit.store import AuditStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{tmpdir}/audit.db"
            client = LocalAuditClient(db_url)
            client.emit_simple(AuditEventType.TEST_GENERATED, actor_id="a", payload={"x": 1})
            client.emit_simple(AuditEventType.CYCLE_COMPLETED, actor_id="a", payload={"success": True})

            independent_store = AuditStore(db_url)
            is_valid, first_invalid = independent_store.verify_full_chain()
            assert is_valid is True, f"false-positive tamper detection at {first_invalid}"

    def test_many_events_verify_clean(self):
        from src.audit.local_client import LocalAuditClient
        from src.audit.schemas import AuditEventType
        from src.audit.store import AuditStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{tmpdir}/audit.db"
            client = LocalAuditClient(db_url)
            for i in range(10):
                client.emit_simple(AuditEventType.CYCLE_COMPLETED, actor_id="a", payload={"i": i})

            is_valid, first_invalid = AuditStore(db_url).verify_full_chain()
            assert is_valid is True, f"false-positive tamper detection at {first_invalid}"

    def test_compute_hash_is_stable_across_naive_and_aware_timestamp_for_same_instant(self):
        """Direct unit check on the root cause, independent of SQLite."""
        from datetime import UTC, datetime

        from src.audit.schemas import AuditEvent, AuditEventType

        aware = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)
        naive = aware.replace(tzinfo=None)  # what SQLite round-trips it as

        event_aware = AuditEvent(
            event_id="e1", event_type=AuditEventType.TEST_GENERATED,
            timestamp=aware, actor_type="agent", actor_id="a",
        )
        event_naive = AuditEvent(
            event_id="e1", event_type=AuditEventType.TEST_GENERATED,
            timestamp=naive, actor_type="agent", actor_id="a",
        )
        assert event_aware.compute_hash() == event_naive.compute_hash()
