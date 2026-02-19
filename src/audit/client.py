"""
Write-only audit client for ACE agents.

This client can ONLY emit audit events. It has no methods to read, query,
modify, or delete audit events. This enforces the audit trail independence
principle at the API level.

Usage:
    client = AuditClient(endpoint="http://ace-audit:8081")
    client.emit(AuditEventCreate(
        event_type=AuditEventType.PATTERN_LEARNED,
        actor_type="agent",
        actor_id="tdd-agent-v1",
        payload={"pattern_id": "ctx-00042", "content_hash": "abc123"}
    ))
"""

import logging
import os
import uuid
from datetime import datetime

import httpx

from src.audit.schemas import AuditEvent, AuditEventCreate, AuditEventType

logger = logging.getLogger(__name__)


class AuditClient:
    """
    Write-only audit client.

    This client enforces the audit trail independence principle:
    - Agents CAN emit events
    - Agents CANNOT read, query, modify, or delete events

    The client is intentionally minimal - it only has emit() method.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        timeout: float = 5.0,
        async_mode: bool = True,
    ):
        """
        Initialize the audit client.

        Args:
            endpoint: Audit service URL (default: from AUDIT_ENDPOINT env var)
            timeout: Request timeout in seconds
            async_mode: If True, emit() is fire-and-forget (non-blocking)
        """
        self.endpoint = endpoint or os.getenv("AUDIT_ENDPOINT", "http://localhost:8081")
        self.timeout = timeout
        self.async_mode = async_mode
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def emit(
        self,
        event: AuditEventCreate,
        *,
        session_id: str | None = None,
        playbook_id: str | None = None,
        project_id: str | None = None,
    ) -> bool:
        """
        Emit an audit event.

        This is a write-only operation. The event is sent to the audit
        service and cannot be retrieved, modified, or deleted by the agent.

        Args:
            event: The event to emit
            session_id: Override session ID (default: from event)
            playbook_id: Override playbook ID (default: from event)
            project_id: Override project ID (default: from event)

        Returns:
            True if event was accepted, False otherwise.
            In async_mode, always returns True (fire-and-forget).
        """
        # Build full event with ID and timestamp
        full_event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=event.event_type,
            timestamp=datetime.utcnow(),
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            session_id=session_id or event.session_id,
            playbook_id=playbook_id or event.playbook_id,
            project_id=project_id or event.project_id,
            payload=event.payload,
        )

        try:
            response = self._get_client().post(
                f"{self.endpoint}/events",
                json=full_event.model_dump(mode="json"),
            )

            if response.status_code == 202:  # Accepted
                logger.debug(f"Audit event emitted: {full_event.event_id}")
                return True
            else:
                logger.warning(
                    f"Audit event rejected: {response.status_code} - {response.text}"
                )
                return False

        except httpx.TimeoutException:
            logger.warning(f"Audit event timeout: {full_event.event_id}")
            return self.async_mode  # In async mode, don't fail on timeout

        except httpx.RequestError as e:
            logger.warning(f"Audit event failed: {e}")
            return self.async_mode  # In async mode, don't fail on network errors

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
        """
        Convenience method to emit an event without creating AuditEventCreate.

        Args:
            event_type: Type of event
            actor_id: ID of the actor (agent name, user email, etc.)
            payload: Event-specific data
            actor_type: Type of actor ('agent', 'human', 'system')
            session_id: Session/conversation ID
            playbook_id: Related playbook
            project_id: Project identifier

        Returns:
            True if event was accepted, False otherwise.
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

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "AuditClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()


class NoOpAuditClient(AuditClient):
    """
    No-op audit client for testing or when audit is disabled.

    Accepts all events but doesn't send them anywhere.
    """

    def emit(self, event: AuditEventCreate, **kwargs) -> bool:
        """Accept event but don't send it."""
        logger.debug(f"NoOp audit: {event.event_type} from {event.actor_id}")
        return True


def get_audit_client() -> AuditClient:
    """
    Get the appropriate audit client based on configuration.

    Returns NoOpAuditClient if audit is disabled or endpoint is not configured.
    """
    endpoint = os.getenv("AUDIT_ENDPOINT")
    if not endpoint or os.getenv("AUDIT_DISABLED", "").lower() == "true":
        return NoOpAuditClient()
    return AuditClient(endpoint=endpoint)
