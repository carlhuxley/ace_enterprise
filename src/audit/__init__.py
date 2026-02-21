"""
ACE Audit Service - Independent audit trail following the audit trail independence principle.

This module provides:
- AuditClient: Write-only client for agents to emit events
- AuditStore: Append-only persistence with hash chain
- AuditCollector: Service that receives and stores events
- AuditAPI: Read-only query interface for compliance/admin

Key principle: Agents can emit audit events but cannot read, modify, or delete them.
The audit service runs as a separate deployment with separate credentials.

Reference: 202602121757-audit-trail-independence-principle.md
"""

from src.audit.client import AuditClient, NoOpAuditClient, get_audit_client
from src.audit.schemas import (
    AuditEvent,
    AuditEventCreate,
    AuditEventType,
    AuditQuery,
    AuditResult,
)
from src.audit.store import AuditStore
from src.audit.dashboard import AgentIdentity, AgentPerformance, AuditDashboard

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
