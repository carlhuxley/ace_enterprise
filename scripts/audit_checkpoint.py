#!/usr/bin/env python3
"""Create or verify external audit-chain checkpoints (ace_enterprise-z8n).

Usage:
    scripts/audit_checkpoint.py create   # snapshot the current chain tip
    scripts/audit_checkpoint.py verify   # check the DB against recorded checkpoints

Set AUDIT_CHECKPOINTS_PATH to use a checkpoints file other than the default
data/audit_checkpoints.jsonl (e.g. for testing against a throwaway DB
without touching the real repo file).

IMPORTANT: `create` only writes to data/audit_checkpoints.jsonl locally. It
does NOT commit or push. A checkpoint provides no tamper-evidence at all
until it's committed and PUSHED to a git remote that the AUDIT_DATABASE_URL
credential does not control — see src/audit/checkpoint.py's module docstring
and docs/adr/003-audit-chain-external-anchoring.md. Run `create` on a
schedule (cron, CI) that also commits and pushes the file.
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.audit.checkpoint import (
    checkpoints_path_from_env,
    create_checkpoint,
    verify_checkpoints,
    write_checkpoint,
)
from src.audit.store import AuditStore


def _get_store() -> AuditStore:
    database_url = os.getenv(
        "AUDIT_DATABASE_URL",
        "postgresql://audit:audit@localhost:5433/ace_audit",
    )
    return AuditStore(database_url)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("create", "verify"):
        print(__doc__)
        sys.exit(1)

    store = _get_store()
    checkpoints_path = checkpoints_path_from_env()

    if sys.argv[1] == "create":
        checkpoint = create_checkpoint(store)
        if checkpoint is None:
            print("Audit store is empty — nothing to checkpoint.")
            return
        write_checkpoint(checkpoint, checkpoints_path)
        print(f"Checkpoint written: {checkpoint.event_count} events, "
              f"tip={checkpoint.last_event_id[:8]}... -> {checkpoints_path}")
        print(
            "\nThis checkpoint provides NO tamper-evidence until it's committed "
            "AND PUSHED to a git remote the audit DB credential does not control:\n"
            f"  git add {checkpoints_path}\n"
            "  git commit -m 'Audit checkpoint'\n"
            "  git push"
        )
        return

    result = verify_checkpoints(store, checkpoints_path)
    print(f"Checked {result.checkpoints_checked} checkpoint(s).")
    if result.valid:
        print("All checkpoints match the live audit chain.")
    else:
        print(f"TAMPER DETECTED — {len(result.failures)} checkpoint(s) failed to verify:")
        for failure in result.failures:
            print(f"  [{failure.checkpoint.created_at}] {failure.reason}")
        sys.exit(1)


if __name__ == "__main__":
    main()
