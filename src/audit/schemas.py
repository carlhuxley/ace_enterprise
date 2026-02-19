"""
Audit event schemas.

These schemas are shared between the audit client (in ACE agents) and
the audit service. They define the structure of audit events and queries.
"""

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    """Types of audit events that can be emitted."""

    # Knowledge events
    KNOWLEDGE_ADDED = "knowledge_added"           # Manual knowledge via CLI
    PATTERN_LEARNED = "pattern_learned"           # AI-extracted pattern
    PATTERN_APPLIED = "pattern_applied"           # Pattern used in generation
    PATTERN_FEEDBACK = "pattern_feedback"         # Helpful/harmful feedback

    # TDD cycle events
    TEST_GENERATED = "test_generated"             # Test code written
    IMPLEMENTATION_GENERATED = "implementation_generated"  # Impl code written
    TEST_EXECUTED = "test_executed"               # Test run result
    CYCLE_COMPLETED = "cycle_completed"           # Full TDD cycle done

    # Agent events
    AGENT_STARTED = "agent_started"               # Agent session began
    AGENT_COMPLETED = "agent_completed"           # Agent session ended
    AGENT_ERROR = "agent_error"                   # Agent encountered error

    # Retrieval events
    RETRIEVAL_QUERY = "retrieval_query"           # Knowledge retrieval request
    RETRIEVAL_RESULT = "retrieval_result"         # What was retrieved

    # System events
    PLAYBOOK_CREATED = "playbook_created"         # New playbook created
    PLAYBOOK_SNAPSHOT = "playbook_snapshot"       # Checkpoint created
    CONFIG_CHANGED = "config_changed"             # Configuration change


class AuditEvent(BaseModel):
    """
    An immutable audit event.

    Once created, audit events cannot be modified or deleted.
    Each event is linked to the previous via hash chain for tamper evidence.
    """

    # Event identification
    event_id: str = Field(..., description="Unique event ID (UUID)")
    event_type: AuditEventType = Field(..., description="Type of event")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Actor information
    actor_type: str = Field(..., description="'human', 'agent', or 'system'")
    actor_id: str = Field(..., description="User email, agent name, or 'system'")

    # Context
    session_id: str | None = Field(None, description="Session/conversation ID")
    playbook_id: str | None = Field(None, description="Related playbook")
    project_id: str | None = Field(None, description="Project identifier")

    # Event payload (type-specific data)
    payload: dict[str, Any] = Field(default_factory=dict)

    # Hash chain for integrity
    prev_hash: str | None = Field(None, description="Hash of previous event")
    event_hash: str | None = Field(None, description="Hash of this event")

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of this event's content."""
        # Exclude hash fields from the hash computation
        content = self.model_dump(exclude={"event_hash"})
        content_str = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(content_str.encode()).hexdigest()

    def with_hash_chain(self, prev_hash: str | None = None) -> "AuditEvent":
        """Return a new event with hash chain fields set."""
        return self.model_copy(update={
            "prev_hash": prev_hash,
            "event_hash": self.model_copy(update={"prev_hash": prev_hash}).compute_hash()
        })


class AuditEventCreate(BaseModel):
    """Schema for creating an audit event (client-side, before hash chain)."""

    event_type: AuditEventType
    actor_type: str
    actor_id: str
    session_id: str | None = None
    playbook_id: str | None = None
    project_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AuditQuery(BaseModel):
    """Query parameters for searching audit events."""

    # Time range
    start_time: datetime | None = None
    end_time: datetime | None = None

    # Filters
    event_types: list[AuditEventType] | None = None
    actor_type: str | None = None
    actor_id: str | None = None
    session_id: str | None = None
    playbook_id: str | None = None
    project_id: str | None = None

    # Pagination
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

    # Ordering
    order_by: str = Field(default="timestamp")
    order_desc: bool = Field(default=True)


class AuditResult(BaseModel):
    """Result of an audit query."""

    events: list[AuditEvent]
    total_count: int
    has_more: bool

    # Integrity verification
    chain_valid: bool = Field(
        default=True,
        description="True if hash chain is intact for returned events"
    )
