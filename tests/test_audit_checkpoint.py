"""Tests for audit chain external anchoring (ace_enterprise-z8n)."""
import os
import uuid

import pytest

from src.audit.checkpoint import (
    DEFAULT_CHECKPOINTS_PATH,
    checkpoints_path_from_env,
    create_checkpoint,
    read_checkpoints,
    verify_checkpoints,
    write_checkpoint,
)
from src.audit.schemas import AuditEvent, AuditEventType
from src.audit.store import AuditStore


def _store(tmp_path):
    store = AuditStore(f"sqlite:///{tmp_path}/audit.db")
    store.create_tables()
    return store


def _append(store, actor_id="agent-1"):
    return store.append(AuditEvent(
        event_id=str(uuid.uuid4()),
        event_type=AuditEventType.AGENT_STARTED,
        actor_type="agent",
        actor_id=actor_id,
    ))


class TestDefaultPathIsRepoRootAnchored:
    def test_default_path_is_absolute(self):
        assert DEFAULT_CHECKPOINTS_PATH.is_absolute()

    def test_default_path_independent_of_cwd(self, tmp_path, monkeypatch):
        """A relative default path would resolve differently depending on
        where the process was launched from -- e.g. a uvicorn worker or cron
        job with a different CWD than the repo root -- silently checking
        zero checkpoints instead of erroring. Must not regress to that."""
        monkeypatch.chdir(tmp_path)
        import importlib
        import src.audit.checkpoint as checkpoint_module
        importlib.reload(checkpoint_module)
        try:
            assert checkpoint_module.DEFAULT_CHECKPOINTS_PATH.is_absolute()
            assert str(checkpoint_module.DEFAULT_CHECKPOINTS_PATH).endswith(
                "data/audit_checkpoints.jsonl"
            )
        finally:
            importlib.reload(checkpoint_module)


class TestCheckpointsPathFromEnv:
    def test_no_override_returns_default(self, monkeypatch):
        monkeypatch.delenv("AUDIT_CHECKPOINTS_PATH", raising=False)
        assert checkpoints_path_from_env() == DEFAULT_CHECKPOINTS_PATH

    def test_override_used_when_set(self, monkeypatch, tmp_path):
        override = tmp_path / "custom_checkpoints.jsonl"
        monkeypatch.setenv("AUDIT_CHECKPOINTS_PATH", str(override))
        assert checkpoints_path_from_env() == override


class TestCreateCheckpoint:
    def test_empty_store_returns_none(self, tmp_path):
        store = _store(tmp_path)
        assert create_checkpoint(store) is None

    def test_matches_latest_event(self, tmp_path):
        store = _store(tmp_path)
        _append(store)
        latest = _append(store)
        checkpoint = create_checkpoint(store)
        assert checkpoint.last_event_id == latest.event_id
        assert checkpoint.last_event_hash == latest.event_hash

    def test_event_count_matches(self, tmp_path):
        store = _store(tmp_path)
        for _ in range(3):
            _append(store)
        checkpoint = create_checkpoint(store)
        assert checkpoint.event_count == 3


class TestWriteAndReadCheckpoints:
    def test_round_trip(self, tmp_path):
        store = _store(tmp_path)
        _append(store)
        checkpoint = create_checkpoint(store)
        path = tmp_path / "checkpoints.jsonl"

        write_checkpoint(checkpoint, path)
        loaded = read_checkpoints(path)

        assert len(loaded) == 1
        assert loaded[0] == checkpoint

    def test_multiple_checkpoints_append(self, tmp_path):
        store = _store(tmp_path)
        path = tmp_path / "checkpoints.jsonl"

        _append(store)
        write_checkpoint(create_checkpoint(store), path)
        _append(store)
        write_checkpoint(create_checkpoint(store), path)

        assert len(read_checkpoints(path)) == 2

    def test_read_missing_file_returns_empty(self, tmp_path):
        assert read_checkpoints(tmp_path / "nope.jsonl") == []

    def test_creates_parent_directories(self, tmp_path):
        store = _store(tmp_path)
        _append(store)
        path = tmp_path / "nested" / "dir" / "checkpoints.jsonl"
        write_checkpoint(create_checkpoint(store), path)
        assert path.exists()


class TestVerifyCheckpoints:
    def test_no_checkpoints_is_valid(self, tmp_path):
        store = _store(tmp_path)
        result = verify_checkpoints(store, tmp_path / "nope.jsonl")
        assert result.valid is True
        assert result.checkpoints_checked == 0

    def test_matching_checkpoint_is_valid(self, tmp_path):
        store = _store(tmp_path)
        _append(store)
        path = tmp_path / "checkpoints.jsonl"
        write_checkpoint(create_checkpoint(store), path)

        result = verify_checkpoints(store, path)
        assert result.valid is True
        assert result.checkpoints_checked == 1
        assert result.failures == []

    def test_multiple_checkpoints_all_valid_across_growth(self, tmp_path):
        """A checkpoint recorded early must still verify after MORE events
        are appended later -- the chain grew, it wasn't rewritten."""
        store = _store(tmp_path)
        path = tmp_path / "checkpoints.jsonl"

        _append(store)
        write_checkpoint(create_checkpoint(store), path)
        _append(store)
        _append(store)
        write_checkpoint(create_checkpoint(store), path)

        result = verify_checkpoints(store, path)
        assert result.valid is True
        assert result.checkpoints_checked == 2

    def test_detects_rewritten_chain(self, tmp_path):
        """The actual attack this exists to catch: wipe the table and
        regenerate a fresh, internally-consistent chain. verify_full_chain()
        alone would pass this; verify_checkpoints() must not."""
        store = _store(tmp_path)
        _append(store)
        _append(store)
        path = tmp_path / "checkpoints.jsonl"
        write_checkpoint(create_checkpoint(store), path)

        # Simulate a privileged DB attacker: wipe and rebuild the chain.
        with store._session() as session:
            from src.audit.store import AuditEventModel
            session.query(AuditEventModel).delete()
        _append(store)  # fresh, internally-consistent chain from scratch

        internally_consistent, _ = store.verify_full_chain()
        assert internally_consistent is True  # the gap this ticket is about

        result = verify_checkpoints(store, path)
        assert result.valid is False
        assert result.checkpoints_checked == 1
        assert len(result.failures) == 1
        assert "no longer exists" in result.failures[0].reason

    def test_detects_hash_mismatch_when_event_id_reused(self, tmp_path):
        """A more surgical tamper: same event_id survives but its content
        (and therefore hash) changed."""
        store = _store(tmp_path)
        event = _append(store)
        path = tmp_path / "checkpoints.jsonl"
        write_checkpoint(create_checkpoint(store), path)

        with store._session() as session:
            from src.audit.store import AuditEventModel
            row = session.query(AuditEventModel).filter(
                AuditEventModel.event_id == event.event_id
            ).first()
            row.event_hash = "0" * 64  # forged hash, same event_id

        result = verify_checkpoints(store, path)
        assert result.valid is False
        assert "hash changed" in result.failures[0].reason
