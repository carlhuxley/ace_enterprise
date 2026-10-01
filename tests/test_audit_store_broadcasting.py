"""Tests for AuditStore.append()'s live-dashboard AuditChainEvent broadcast."""
import uuid
from unittest.mock import patch

from src.audit.schemas import AuditEvent, AuditEventType
from src.audit.store import AuditStore


def _store(tmp_path):
    store = AuditStore(f"sqlite:///{tmp_path}/audit.db")
    store.create_tables()
    return store


def _event(actor_id="agent-1"):
    return AuditEvent(
        event_id=str(uuid.uuid4()),
        event_type=AuditEventType.AGENT_STARTED,
        actor_type="agent",
        actor_id=actor_id,
    )


class TestAuditChainBroadcasting:
    def test_append_broadcasts_the_real_hash_chain_fields(self, tmp_path):
        store = _store(tmp_path)
        with patch("src.ui.broadcaster.broadcast_event") as mock_broadcast:
            appended = store.append(_event())

        mock_broadcast.assert_called_once()
        (event,), _ = mock_broadcast.call_args
        assert event.event_type == AuditEventType.AGENT_STARTED.value
        assert event.event_hash == appended.event_hash
        assert event.prev_hash == appended.prev_hash
        assert event.prev_hash is None  # first event in the chain

    def test_second_event_broadcasts_the_prior_hash_as_prev_hash(self, tmp_path):
        store = _store(tmp_path)
        first = store.append(_event())
        with patch("src.ui.broadcaster.broadcast_event") as mock_broadcast:
            store.append(_event(actor_id="agent-2"))

        (event,), _ = mock_broadcast.call_args
        assert event.prev_hash == first.event_hash
