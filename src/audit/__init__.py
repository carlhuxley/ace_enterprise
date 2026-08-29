"""
ACE Audit Service - Independent audit trail following the audit trail independence principle.

This module provides:
- AuditClient: Write-only client for agents to emit events
- AuditStore: Append-only persistence with hash chain
- AuditCollector: Service that receives and stores events
- AuditAPI: Read-only query interface for compliance/admin

Key principle: Agents can emit audit events but cannot read, modify, or delete them.
The audit service runs as a separate deployment with separate credentials.

Reference: docs/adr/001-audit-trail-independence.md
"""

from src.audit.client import AuditClient, NoOpAuditClient, get_audit_client
from src.audit.dashboard import AgentIdentity, AgentPerformance, AuditDashboard
from src.audit.schemas import (
    AuditEvent,
    AuditEventCreate,
    AuditEventType,
    AuditQuery,
    AuditResult,
)
from src.audit.store import AuditStore

__all__ = [
    # Schemas
    "AuditEvent",
    "AuditEventCreate",
    "AuditEventType",
    "AuditQuery",
    "AuditResult",
    # Client (for agents)
    "AuditClient",
    "NoOpAuditClient",
    "get_audit_client",
    # Store (for audit service)
    "AuditStore",
    # Dashboard (for humans)
    "AgentIdentity",
    "AgentPerformance",
    "AuditDashboard",
]
