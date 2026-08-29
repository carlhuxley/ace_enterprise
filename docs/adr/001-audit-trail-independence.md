# ADR 001 — Audit Trail Independence

**Status:** Accepted
**Date:** 2026-02-12

## Context

A monitoring system that is controlled by the thing it monitors provides no
real guarantee. If an agent (or the application it's embedded in) can read,
modify, or delete its own audit trail, the trail proves nothing under the
threat model that actually matters — a compromised or misbehaving agent.

## Decision

Build the audit trail outside the monitored system's access, not just
logically separate but architecturally independent:

- **Independent** — the audit mechanism is a distinct system from what it
  monitors, not a module within it
- **External** — it sits outside the boundary an attacker who compromises
  the monitored system would control
- **Separate** — its own storage and credentials, so integrity doesn't rely
  on the monitored system behaving correctly

This is the standard rationale behind centralized logging separated from
application servers, external SIEM systems, and immutable audit logs in
independent storage.

## Consequences

- `src/audit/` is architected so agents can only *emit* events (`AuditClient`,
  write-only) — they have no read, modify, or delete access to the store
  they write to.
- The audit collector (`src/audit/collector.py`) accepts only `POST /events`;
  querying is a separate read-only service (`src/audit/api.py`).
- `services/ace-audit/` deploys the audit store as a separate service with
  its own database, protecting against the *main application* compromising
  the audit trail.
- This principle has a gap by itself: it protects against the monitored
  system reaching into the audit trail, but not against someone with direct
  access to the audit store's own credentials rewriting history
  consistently. See [ADR 003](003-audit-chain-external-anchoring.md) for the
  external-anchoring mechanism that closes that gap.

## Related concepts

Principle of least privilege, defense in depth, trust but verify, security
by design.
