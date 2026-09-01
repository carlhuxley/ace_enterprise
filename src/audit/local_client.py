"""Local audit client for development/testing.

This client writes directly to a local SQLite database instead of
going through HTTP. Use this for local development when you don't
have a full audit service running.

Usage:
    from src.audit.local_client import get_local_audit_client

    client = get_local_audit_client()
    client.emit_simple(
        AuditEventType.PATTERN_LEARNED,
        actor_id="tdd-agent",
        payload={"pattern_id": "ctx-001"}
    )
"""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from src.audit.schemas import AuditEvent, AuditEventCreate, AuditEventType
from src.audit.store import AuditStore

logger = logging.getLogger(__name__)


def default_local_audit_url() -> str:
    """SQLite URL for the default local audit database (.local/audit.db).

    Single source of truth for the path, shared by LocalAuditClient (writes)
    and the broker's read-only PerformanceAggregator path.
    """
    project_root = Path(__file__).parent.parent.parent
    db_path = project_root / ".local" / "audit.db"
    db_path.parent.mkdir(exist_ok=True)
    return f"sqlite:///{db_path}"


class LocalAuditClient:
    """Audit client that writes directly to local SQLite database.

    This bypasses the HTTP service for local development.
    Still enforces write-only semantics (no read methods exposed).
    """

    def __init__(self, database_url: str | None = None) -> None:
        """Initialize local audit client.

        Args:
            database_url: SQLite URL. Defaults to .local/audit.db
        """
        if database_url is None:
            database_url = default_local_audit_url()

        self._store = AuditStore(database_url)
        self._store.create_tables()
        self._database_url = database_url

    @property
    def database_url(self) -> str:
        """The audit database this client writes to.

        Exposed (read-only) so the broker's PerformanceAggregator can open its
        own read connection against the same store without the client leaking
        its write-capable AuditStore.
        """
        return self._database_url

    def emit(
        self,
        event: AuditEventCreate,
        *,
        session_id: str | None = None,
        playbook_id: str | None = None,
        project_id: str | None = None,
    ) -> bool:
        """Emit an audit event to local database.

        Args:
            event: The event to emit
            session_id: Override session ID
            playbook_id: Override playbook ID
            project_id: Override project ID

        Returns:
            True if event was stored successfully
        """
        full_event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=event.event_type,
            timestamp=datetime.now(UTC),
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            session_id=session_id or event.session_id,
            playbook_id=playbook_id or event.playbook_id,
            project_id=project_id or event.project_id,
            payload=event.payload,
        )

        try:
            self._store.append(full_event)
            logger.debug(f"Local audit event stored: {full_event.event_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to store audit event: {e}")
            return False

    def emit_simple(
        self,
        event_type: AuditEventType,
        actor_id: str,
        payload: dict | None = None,
        *,
        actor_type: str = "agent",
        session_id: str | None = None,
        playbook_id: str | None = None,
        project_id: str | None = None,
    ) -> bool:
        """Convenience method to emit an event.

        Args:
            event_type: Type of event
            actor_id: ID of the actor
            payload: Event-specific data
            actor_type: Type of actor
            session_id: Session ID
            playbook_id: Playbook ID
            project_id: Project ID

        Returns:
            True if event was stored successfully
        """
        event = AuditEventCreate(
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            session_id=session_id,
            playbook_id=playbook_id,
            project_id=project_id,
            payload=payload or {},
        )
        return self.emit(event)

    def get_stats(self) -> dict:
        """Get audit statistics (for debugging/testing only)."""
        return self._store.get_stats()

    def close(self) -> None:
        """Close the database connection."""
        pass  # SQLAlchemy handles connection pooling

    def __enter__(self) -> "LocalAuditClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()


def get_local_audit_client(database_url: str | None = None) -> LocalAuditClient:
    """Get a local audit client.

    Args:
        database_url: Optional database URL. Defaults to .local/audit.db

    Returns:
        LocalAuditClient instance
    """
    return LocalAuditClient(database_url)
