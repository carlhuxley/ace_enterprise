"""External anchoring for the audit hash chain (ace_enterprise-z8n).

verify_full_chain() (src/audit/store.py) proves internal consistency: every
row's event_hash matches its content, and every row's prev_hash matches the
previous row's event_hash. It does NOT prove the chain hasn't been rewritten
wholesale — anyone with write access to the audit_events table (a compromised
AUDIT_DATABASE_URL credential, an insider, a DB admin) can recompute a fresh,
internally-consistent chain from scratch and verify_full_chain() will still
pass, because the check has nothing outside the table to compare against.

This module adds that missing external reference point: periodically record
the most recent event's id and hash into a small JSONL file
(data/audit_checkpoints.jsonl) that gets committed to git. Verification later
confirms the DB still produces that exact hash at that position. Because the
hash chain is cumulative (SHA-256 over each event's content plus the previous
event's hash), matching a single checkpoint proves the ENTIRE prefix up to
that point is unchanged — you cannot alter an earlier event without changing
every hash after it.

*** THIS ONLY WORKS IF THE CHECKPOINT COMMITS ARE ACTUALLY PUSHED to a git
remote that the audit-DB credential does not control. *** A checkpoint that
only exists as a local, uncommitted (or committed-but-unpushed) file provides
NO protection: the same attacker who can rewrite the DB can just as easily
rewrite or delete a local checkpoint file to match. This module deliberately
does not run `git commit`/`git push` itself — call create_checkpoint() +
write_checkpoint() from a scheduled job (cron, CI, a periodic script) that
you control, and that job must commit AND push for the anchor to mean
anything. See docs/adr/003-audit-chain-external-anchoring.md.
"""
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.audit.store import AuditStore

# Anchored to the repo root, not CWD: a relative path here would silently
# report "0 checkpoints found" (not an error) whenever this module is
# imported from a different working directory (a uvicorn worker, a cron job
# run from elsewhere) -- for a security check, "silently checked nothing"
# reading as "passed" is worse than a loud failure.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CHECKPOINTS_PATH = _REPO_ROOT / "data" / "audit_checkpoints.jsonl"


def checkpoints_path_from_env() -> Path:
    """AUDIT_CHECKPOINTS_PATH overrides the default, e.g. for a deployment
    that stores it elsewhere, or for testing against a throwaway path
    without touching the real repo file. Shared by scripts/audit_checkpoint.py
    and the /verify API route so they can't drift out of sync."""
    override = os.getenv("AUDIT_CHECKPOINTS_PATH")
    return Path(override) if override else DEFAULT_CHECKPOINTS_PATH


@dataclass
class AuditCheckpoint:
    created_at: str
    event_count: int
    last_event_id: str
    last_event_hash: str


@dataclass
class CheckpointFailure:
    checkpoint: AuditCheckpoint
    reason: str


@dataclass
class CheckpointVerificationResult:
    valid: bool
    checkpoints_checked: int
    failures: list[CheckpointFailure]


def create_checkpoint(store: AuditStore) -> AuditCheckpoint | None:
    """Snapshot the current chain tip. Returns None if the store is empty."""
    stats = store.get_stats()
    event_count = stats["total_events"]
    if not event_count:
        return None

    last_hash = store._last_event_hash()
    if last_hash is None:
        return None
    last_id, last_event_hash = last_hash

    return AuditCheckpoint(
        created_at=datetime.now(UTC).isoformat(),
        event_count=event_count,
        last_event_id=last_id,
        last_event_hash=last_event_hash,
    )


def write_checkpoint(
    checkpoint: AuditCheckpoint, path: Path = DEFAULT_CHECKPOINTS_PATH
) -> None:
    """Append a checkpoint to the JSONL file. Does not commit or push —
    see module docstring: that's the operator's responsibility."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(asdict(checkpoint)) + "\n")


def read_checkpoints(path: Path = DEFAULT_CHECKPOINTS_PATH) -> list[AuditCheckpoint]:
    if not path.exists():
        return []
    checkpoints = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            checkpoints.append(AuditCheckpoint(**json.loads(line)))
    return checkpoints


def verify_checkpoints(
    store: AuditStore, path: Path = DEFAULT_CHECKPOINTS_PATH
) -> CheckpointVerificationResult:
    """Confirm the live DB still produces every previously-recorded checkpoint
    hash at its recorded event_id. A mismatch (or a missing event_id) means
    the chain was rewritten at or before that checkpoint.

    Only meaningful if the checkpoints file itself was loaded from a trusted,
    pushed git ref rather than the same filesystem the DB attacker could also
    reach — see module docstring.
    """
    checkpoints = read_checkpoints(path)
    failures: list[CheckpointFailure] = []

    for checkpoint in checkpoints:
        actual_hash = store._event_hash_by_id(checkpoint.last_event_id)
        if actual_hash is None:
            failures.append(CheckpointFailure(
                checkpoint=checkpoint,
                reason=f"event {checkpoint.last_event_id} no longer exists in the DB",
            ))
        elif actual_hash != checkpoint.last_event_hash:
            failures.append(CheckpointFailure(
                checkpoint=checkpoint,
                reason=(
                    f"event {checkpoint.last_event_id} hash changed: "
                    f"checkpointed {checkpoint.last_event_hash}, DB now has {actual_hash}"
                ),
            ))

    return CheckpointVerificationResult(
        valid=len(failures) == 0,
        checkpoints_checked=len(checkpoints),
        failures=failures,
    )
