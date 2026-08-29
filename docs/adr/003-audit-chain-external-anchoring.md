# ADR 003 — Audit Chain External Anchoring

**Status:** Accepted
**Date:** 2026-08-09
**Issue:** ace_enterprise-z8n

## Context

`AuditStore.verify_full_chain()` proves internal self-consistency: every row's
`event_hash` matches its own content, and every row's `prev_hash` matches the
previous row's `event_hash`. It does not — and cannot — prove the chain
hasn't been rewritten wholesale, because the entire check runs against the
same table an attacker with write access would rewrite. Anyone holding the
`AUDIT_DATABASE_URL` credential (a compromised secret, a DB admin, an
insider) can regenerate a fresh, internally-consistent chain from scratch and
`verify_full_chain()` will still return `True`.

This directly contradicts the project's own stated principle
([ADR 001](001-audit-trail-independence.md)): build the audit trail outside
the monitored system's access — a system that controls its own monitoring
provides no real guarantee. `services/ace-audit/` already
deploys the audit store as a separate service with its own database, which
protects against the *main application* compromising the audit trail — but
it does nothing against direct compromise of the audit DB's own credential,
which is a narrower but still realistic threat.

This was deliberately triaged as P3, not P0/P1: the threat model (a
privileged/compromised credential belonging to someone *other* than the
operator) doesn't apply while ACE Enterprise is single-user. It matters once
there are multiple operators, or once the audit trail needs to be trusted
against its own administrators.

## Decision

Add a lightweight external anchor: periodically snapshot the chain's tip
(`event_id` + `event_hash` of the most recent event, plus event count) into
`data/audit_checkpoints.jsonl`, and commit that file to git.

Because the hash chain is cumulative — each event's hash is computed over
its own content plus the previous event's hash — matching a single
checkpoint proves the *entire prefix* up to that point is unchanged. You
cannot alter an early event without changing every hash computed after it,
including the one recorded in the checkpoint.

Implementation: `src/audit/checkpoint.py` (`create_checkpoint`,
`write_checkpoint`, `verify_checkpoints`), a CLI wrapper
(`scripts/audit_checkpoint.py create|verify`), and the audit API's `/verify`
endpoint now also reports `checkpoint_valid`/`checkpoints_checked` alongside
the existing internal `chain_valid` check.

## Why git, not signing or WORM storage

Two stronger alternatives were considered and rejected for now, not because
they're wrong in principle but because they don't fit where this project
actually is:

- **Cryptographic signing** with a key held outside the DB role would be a
  stronger guarantee, but only if signing happens in a genuinely separate
  trust boundary from whatever writes to the DB — not just "the same process
  also holds a key." That requires real key-management infrastructure
  (generation, storage, rotation) this project doesn't have yet.
- **WORM storage** (S3 Object Lock or equivalent) is the strongest option,
  but requires cloud infrastructure this project doesn't currently deploy —
  it runs on docker-compose today, not in a cloud account.

Git-anchored checkpoints reuse a pattern already proven in this exact
codebase: `bootstrap/orchestrate.py` already copies its own audit log
(`bootstrap/audit_log.py`'s `BootstrapAuditLog`, a separate hash-chained
JSONL system for the private→OSS pipeline) into the public OSS repo and
commits it on every run. This ADR applies the same idea to the main
`AuditStore`.

## THE LIMITATION — read this before relying on it

**A checkpoint provides zero tamper-evidence until it is committed AND
PUSHED to a git remote that the audit-DB credential does not control.**

`scripts/audit_checkpoint.py create` only writes a local file. It
deliberately does not run `git commit` or `git push` itself. If checkpoints
are only ever written locally, or committed but never pushed, an attacker
capable of rewriting the audit DB can just as easily rewrite or delete the
local checkpoint file to match — the "external" anchor isn't external at
all in that case, it's sitting on the same machine as the thing it's meant
to catch.

For this to mean anything in practice:

1. `create` must run on a schedule (cron, a CI job, anything outside the
   application's own runtime) that you control independently of the audit
   DB credential.
2. That job must `git commit` **and `git push`** the checkpoints file to a
   remote — GitHub, a separate git server, anywhere the attacker's
   compromised credential doesn't also grant push access.
3. `verify` must be run against a checkpoints file that was `git pull`ed
   from that trusted remote, not just whatever happens to be sitting on
   disk locally.

None of this is wired up automatically today. This ADR adds the mechanism;
operationalizing it (the actual cron/CI job, remote access separation) is a
deployment decision for whoever runs ACE Enterprise beyond single-user local
dev, and is out of scope until `ace_enterprise-z8n`'s original P0→P3
re-triage condition — multiple operators, or the audit trail needing to be
trusted against its own admins — actually applies.
