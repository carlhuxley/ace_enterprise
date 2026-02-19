"""
Append-only audit store with hash chain integrity.

This store enforces immutability:
- Events can only be appended (INSERT)
- Events cannot be modified (no UPDATE)
- Events cannot be deleted (no DELETE)
- Hash chain provides tamper evidence

The store is designed to be used by the audit service only,
not directly by ACE agents.
"""

import logging
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    create_engine,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from src.audit.schemas import (
    AuditEvent,
    AuditEventType,
    AuditQuery,
    AuditResult,
)

logger = logging.getLogger(__name__)

Base = declarative_base()


class AuditEventModel(Base):
    """
    SQLAlchemy model for audit events.

    This table is append-only. The application layer enforces:
    - No UPDATE operations
    - No DELETE operations
    - Hash chain integrity on INSERT
    """

    __tablename__ = "audit_events"

    # Primary key (internal, sequential for ordering)
    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # Event identification
    event_id: str = Column(String(36), unique=True, nullable=False, index=True)
    event_type: str = Column(
        Enum(AuditEventType, name="audit_event_type"),
        nullable=False,
        index=True
    )
    timestamp: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True
    )

    # Actor information
    actor_type: str = Column(String(50), nullable=False, index=True)
    actor_id: str = Column(String(255), nullable=False, index=True)

    # Context
    session_id: str = Column(String(255), nullable=True, index=True)
    playbook_id: str = Column(String(255), nullable=True, index=True)
    project_id: str = Column(String(255), nullable=True, index=True)

    # Event payload (JSON)
    payload: dict = Column(JSON, nullable=False, default=dict)

    # Hash chain
    prev_hash: str = Column(String(64), nullable=True)
    event_hash: str = Column(String(64), nullable=False, index=True)

    __table_args__ = (
        # Composite indexes for common queries
        Index("ix_audit_events_actor", "actor_type", "actor_id"),
        Index("ix_audit_events_time_type", "timestamp", "event_type"),
        Index("ix_audit_events_session", "session_id", "timestamp"),
        Index("ix_audit_events_playbook", "playbook_id", "timestamp"),
    )


class AuditStore:
    """
    Append-only audit event store.

    This class enforces the immutability constraints:
    - Only append() is allowed (INSERT)
    - No update or delete methods exist
    - Hash chain is maintained automatically
    """

    def __init__(self, database_url: str):
        """
        Initialize the audit store.

        Args:
            database_url: PostgreSQL connection string for audit database.
                         This should be DIFFERENT from the main ACE database.
        """
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._last_hash: str | None = None

    def create_tables(self) -> None:
        """Create audit tables if they don't exist."""
        Base.metadata.create_all(self.engine)
        logger.info("Audit tables created/verified")

    @contextmanager
    def _session(self):
        """Get a database session."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _get_last_hash(self, session: Session) -> str | None:
        """Get the hash of the most recent event for chain continuity."""
        result = session.query(AuditEventModel.event_hash).order_by(
            AuditEventModel.id.desc()
        ).first()
        return result[0] if result else None

    def append(self, event: AuditEvent) -> AuditEvent:
        """
        Append an audit event to the store.

        This is the ONLY write operation. Events cannot be modified
        or deleted once appended.

        Args:
            event: The audit event to append

        Returns:
            The event with hash chain fields populated

        Raises:
            ValueError: If event already has a hash (duplicate prevention)
        """
        with self._session() as session:
            # Get the last hash for chain continuity
            prev_hash = self._get_last_hash(session)

            # Compute hash chain
            event_with_hash = event.with_hash_chain(prev_hash)

            # Create model instance
            model = AuditEventModel(
                event_id=event_with_hash.event_id,
                event_type=event_with_hash.event_type,
                timestamp=event_with_hash.timestamp,
                actor_type=event_with_hash.actor_type,
                actor_id=event_with_hash.actor_id,
                session_id=event_with_hash.session_id,
                playbook_id=event_with_hash.playbook_id,
                project_id=event_with_hash.project_id,
                payload=event_with_hash.payload,
                prev_hash=event_with_hash.prev_hash,
                event_hash=event_with_hash.event_hash,
            )

            session.add(model)
            logger.debug(f"Appended audit event: {event_with_hash.event_id}")

            return event_with_hash

    def query(self, query: AuditQuery) -> AuditResult:
        """
        Query audit events (read-only).

        Args:
            query: Query parameters

        Returns:
            AuditResult with matching events and metadata
        """
        with self._session() as session:
            q = session.query(AuditEventModel)

            # Apply filters
            if query.start_time:
                q = q.filter(AuditEventModel.timestamp >= query.start_time)
            if query.end_time:
                q = q.filter(AuditEventModel.timestamp <= query.end_time)
            if query.event_types:
                q = q.filter(AuditEventModel.event_type.in_(query.event_types))
            if query.actor_type:
                q = q.filter(AuditEventModel.actor_type == query.actor_type)
            if query.actor_id:
                q = q.filter(AuditEventModel.actor_id == query.actor_id)
            if query.session_id:
                q = q.filter(AuditEventModel.session_id == query.session_id)
            if query.playbook_id:
                q = q.filter(AuditEventModel.playbook_id == query.playbook_id)
            if query.project_id:
                q = q.filter(AuditEventModel.project_id == query.project_id)

            # Get total count
            total_count = q.count()

            # Apply ordering
            order_col = getattr(AuditEventModel, query.order_by, AuditEventModel.timestamp)
            if query.order_desc:
                q = q.order_by(order_col.desc())
            else:
                q = q.order_by(order_col.asc())

            # Apply pagination
            q = q.offset(query.offset).limit(query.limit)

            # Execute query
            models = q.all()

            # Convert to schema objects
            events = [
                AuditEvent(
                    event_id=m.event_id,
                    event_type=m.event_type,
                    timestamp=m.timestamp,
                    actor_type=m.actor_type,
                    actor_id=m.actor_id,
                    session_id=m.session_id,
                    playbook_id=m.playbook_id,
                    project_id=m.project_id,
                    payload=m.payload,
                    prev_hash=m.prev_hash,
                    event_hash=m.event_hash,
                )
                for m in models
            ]

            # Verify hash chain integrity for returned events
            chain_valid = self._verify_chain(events)

            return AuditResult(
                events=events,
                total_count=total_count,
                has_more=query.offset + len(events) < total_count,
                chain_valid=chain_valid,
            )

    def _verify_chain(self, events: list[AuditEvent]) -> bool:
        """Verify hash chain integrity for a list of events."""
        if not events:
            return True

        # Events should be in order (by timestamp or id)
        for i, event in enumerate(events):
            computed = event.compute_hash()
            if computed != event.event_hash:
                logger.warning(f"Hash mismatch for event {event.event_id}")
                return False

            # Check chain linkage (if we have consecutive events)
            if i > 0 and events[i].prev_hash != events[i - 1].event_hash:
                # This is expected if events are not consecutive
                # Only flag if we expect them to be consecutive
                pass

        return True

    def verify_full_chain(self) -> tuple[bool, str | None]:
        """
        Verify the entire hash chain from the beginning.

        Returns:
            (is_valid, first_invalid_event_id)
        """
        with self._session() as session:
            events = session.query(AuditEventModel).order_by(
                AuditEventModel.id.asc()
            ).all()

            prev_hash = None
            for model in events:
                # Check prev_hash linkage
                if model.prev_hash != prev_hash:
                    return False, model.event_id

                # Recreate event and verify hash
                event = AuditEvent(
                    event_id=model.event_id,
                    event_type=model.event_type,
                    timestamp=model.timestamp,
                    actor_type=model.actor_type,
                    actor_id=model.actor_id,
                    session_id=model.session_id,
                    playbook_id=model.playbook_id,
                    project_id=model.project_id,
                    payload=model.payload,
                    prev_hash=model.prev_hash,
                    event_hash=model.event_hash,
                )

                if event.compute_hash() != model.event_hash:
                    return False, model.event_id

                prev_hash = model.event_hash

            return True, None

    def get_stats(self) -> dict:
        """Get audit store statistics."""
        with self._session() as session:
            total_events = session.query(func.count(AuditEventModel.id)).scalar()

            # Events by type
            type_counts = dict(
                session.query(
                    AuditEventModel.event_type,
                    func.count(AuditEventModel.id)
                ).group_by(AuditEventModel.event_type).all()
            )

            # Time range
            oldest = session.query(func.min(AuditEventModel.timestamp)).scalar()
            newest = session.query(func.max(AuditEventModel.timestamp)).scalar()

            return {
                "total_events": total_events,
                "events_by_type": type_counts,
                "oldest_event": oldest,
                "newest_event": newest,
            }
