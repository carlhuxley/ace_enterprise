#!/usr/bin/env python3
"""CLI bridge for dream_rsi's offline audit-ingestion/pruning driver.

dream_rsi's dream_runner.py never imports ace_enterprise's Python code
directly (see specs/features/audit_ingestion_and_pruning_driver.feature and
specs/contracts/playbook_pruner.contract.yml in that repo) -- it shells into
this script, in this repo's own venv, to read causal uplift and to mutate a
real playbook + audit log.

Usage:
    reliability_cli.py uplift --playbook-id ID [--ace-root PATH] [--min-samples N]
    reliability_cli.py deprecate --playbook-id ID --bullet-id ID --reason TEXT [--ace-root PATH]

Both subcommands print one JSON object to stdout and exit non-zero (with a
JSON error object on stderr) on failure -- deprecate makes no change to the
playbook or audit log when it fails.
"""
import argparse
import dataclasses
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.audit.local_client import LocalAuditClient  # noqa: E402
from src.audit.store import AuditStore  # noqa: E402
from src.reliability.playbook_analyzer import PlaybookReliabilityAnalyzer  # noqa: E402

# PlaybookManager is imported lazily, inside cmd_deprecate only: it pulls in
# src.utils.embedding -> sentence_transformers/torch at module level, a
# ~6s import cost paid even if a PlaybookManager is never constructed.
# `uplift` doesn't need one at all (see cmd_uplift below) and is called once
# per playbook by dream_runner.py -- eating that cost unconditionally here
# made every uplift subprocess call slow across a real project's full
# playbook set.


def _audit_url(ace_root: Path) -> str:
    return f"sqlite:///{ace_root / '.local' / 'audit.db'}"


def _fail(message: str) -> None:
    print(json.dumps({"error": message}), file=sys.stderr)
    sys.exit(1)


def _require_audit_db(ace_root: Path) -> Path:
    db_path = ace_root / ".local" / "audit.db"
    if not db_path.exists():
        _fail(f"no audit database at {db_path}")
    return db_path


def cmd_uplift(args: argparse.Namespace) -> None:
    ace_root = Path(args.ace_root)
    _require_audit_db(ace_root)

    # No PlaybookManager here: bullet_uplift() is audit-log-only (see
    # PlaybookReliabilityAnalyzer's docstring) -- constructing one would
    # load and parse every playbook file under data/playbooks/ for no
    # reason, which is what made dream_runner.py's per-playbook uplift
    # sweep slow against a real project with ~140 playbook files.
    store = AuditStore(_audit_url(ace_root))
    analyzer = PlaybookReliabilityAnalyzer(store)
    results = analyzer.bullet_uplift(args.playbook_id, min_samples=args.min_samples)
    print(json.dumps([dataclasses.asdict(r) for r in results]))


def cmd_deprecate(args: argparse.Namespace) -> None:
    from src.playbook.manager import PlaybookManager

    ace_root = Path(args.ace_root)
    _require_audit_db(ace_root)

    audit_client = LocalAuditClient(_audit_url(ace_root))
    manager = PlaybookManager(storage_path=str(ace_root / "data" / "playbooks"))
    try:
        removed = manager.deprecate_bullet(
            args.playbook_id, args.bullet_id, args.reason,
            audit_client=audit_client, actor_id="dream-rsi-pruner",
        )
    except ValueError as exc:
        _fail(str(exc))
    print(json.dumps({"removed": removed}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    uplift = sub.add_parser("uplift", help="print causal uplift per bullet as JSON")
    uplift.add_argument("--playbook-id", required=True)
    uplift.add_argument("--ace-root", default=str(project_root))
    uplift.add_argument("--min-samples", type=int, default=1)
    uplift.set_defaults(func=cmd_uplift)

    deprecate = sub.add_parser("deprecate", help="remove a bullet and emit the audit event")
    deprecate.add_argument("--playbook-id", required=True)
    deprecate.add_argument("--bullet-id", required=True)
    deprecate.add_argument("--reason", required=True)
    deprecate.add_argument("--ace-root", default=str(project_root))
    deprecate.set_defaults(func=cmd_deprecate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
