"""Verify the bootstrap audit chain and file integrity.

Checks:
  1. Chain integrity — re-derives every chain_hash to confirm the log has not
     been modified or reordered after the fact.
  2. File integrity — for every file whose sha256 was recorded in the log,
     confirms the on-disk file still matches. Uses the LAST recorded hash for
     each path so legitimate re-synthesis and manual edits are handled correctly.
     Files that were intentionally deleted by the pipeline (CLEAN_ROOM_FAIL,
     STYLE_BLOCK) are skipped rather than flagged as missing.

Coverage gaps (files recorded without a sha256):
  PACKAGE_JSON_WRITE, TSCONFIG_WRITE, PYPROJECT_WRITE — path only, not verifiable.
  Pre-patch SYNTHESIS_CACHED entries — no file_hashes field; those modules
  will show as "unverifiable (pre-patch)" in the summary.

Usage:
  python bootstrap/verify.py [--log bootstrap/audit.jsonl]

Exit codes:
  0  All checks passed
  1  One or more checks failed
"""
import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_LOG = Path("bootstrap/audit.jsonl")

# Events where the named file should still exist — (path_field, hash_field)
_EXIST_EVENTS: dict[str, tuple[str, str]] = {
    "GHERKIN_EMIT":    ("feature_file", "sha256"),
    "GHERKIN_MANUAL":  ("feature_file", "sha256"),
    "GHERKIN_CACHED":  ("feature_file", "sha256"),
    "CLEAN_ROOM_PASS": ("file",         "sha256"),
    "STAMP_APPLY":     ("file",         "sha256"),
    "LICENSE_WRITE":   ("path",         "sha256"),
}

# Events where the pipeline deleted the file immediately after logging
_DELETED_EVENTS = {"CLEAN_ROOM_FAIL", "STYLE_BLOCK"}


@dataclass
class _FileRecord:
    sha256: str
    event: str
    deleted: bool = False


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_entries(log_path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _check_chain(entries: list[dict]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    prev = "0" * 64
    for i, entry in enumerate(entries):
        recorded = entry.get("chain_hash", "")
        payload = {k: v for k, v in entry.items() if k != "chain_hash"}
        expected = hashlib.sha256(
            (prev + json.dumps(payload, sort_keys=True)).encode()
        ).hexdigest()
        if recorded != expected:
            errors.append(
                f"entry {i}  event={entry.get('event')}  ts={entry.get('ts', '?')}\n"
                f"  expected chain_hash {expected[:16]}…\n"
                f"  recorded chain_hash {recorded[:16]}…"
            )
            break  # subsequent entries cannot be trusted once chain is broken
        prev = recorded
    return not errors, errors


def _build_file_map(entries: list[dict]) -> tuple[dict[str, _FileRecord], int]:
    """Return (path -> FileRecord, pre_patch_cached_count)."""
    records: dict[str, _FileRecord] = {}
    pre_patch_cached = 0

    for entry in entries:
        event = entry.get("event", "")

        if event in _EXIST_EVENTS:
            path_key, hash_key = _EXIST_EVENTS[event]
            path = entry.get(path_key)
            sha = entry.get(hash_key)
            if path and sha:
                records[path] = _FileRecord(sha256=sha, event=event)

        elif event in _DELETED_EVENTS:
            path = entry.get("file")
            sha = entry.get("sha256")
            if path and sha:
                records[path] = _FileRecord(sha256=sha, event=event, deleted=True)

        elif event == "SYNTHESIS_CACHED":
            file_hashes: dict = entry.get("file_hashes", {})
            out_dir = entry.get("out_dir", "")
            if not file_hashes:
                pre_patch_cached += 1
                continue
            for name, sha in file_hashes.items():
                path = str(Path(out_dir) / name)
                records[path] = _FileRecord(sha256=sha, event=event)

    return records, pre_patch_cached


def _check_files(
    records: dict[str, _FileRecord],
) -> tuple[bool, list[str], list[str], int]:
    tampered: list[str] = []
    missing: list[str] = []
    verified = 0

    for path_str, rec in sorted(records.items()):
        if rec.deleted:
            continue
        path = Path(path_str)
        if not path.exists():
            missing.append(f"{path_str}  [{rec.event}]")
            continue
        actual = _sha256(path)
        if actual != rec.sha256:
            tampered.append(
                f"{path_str}\n"
                f"  recorded  {rec.sha256}\n"
                f"  on disk   {actual}\n"
                f"  last event {rec.event}"
            )
        else:
            verified += 1

    return not tampered, tampered, missing, verified


def verify(log_path: Path = _DEFAULT_LOG) -> bool:
    if not log_path.exists():
        print(f"ERROR  audit log not found: {log_path}")
        return False

    entries = _load_entries(log_path)
    print(f"Loaded {len(entries)} log entries from {log_path}\n")

    # 1. Chain integrity
    print("=== 1. Chain integrity ===")
    chain_ok, chain_errors = _check_chain(entries)
    if chain_ok:
        print(f"  OK   {len(entries)} entries verified")
    else:
        for e in chain_errors:
            for line in e.splitlines():
                print(f"  FAIL {line}")
    print()

    # 2. File integrity
    print("=== 2. File integrity ===")
    records, pre_patch_cached = _build_file_map(entries)
    verifiable = sum(1 for r in records.values() if not r.deleted)
    files_ok, tampered, missing, verified = _check_files(records)

    print(f"  Tracked paths          {len(records)}")
    print(f"  Verifiable             {verifiable}  (deleted entries excluded)")
    print(f"  Verified OK            {verified}")
    if pre_patch_cached:
        print(f"  Unverifiable (pre-patch SYNTHESIS_CACHED)  {pre_patch_cached} runs")

    if missing:
        print(f"\n  WARN  {len(missing)} tracked file(s) absent from disk:")
        for m in missing:
            print(f"    {m}")

    if tampered:
        print(f"\n  FAIL  {len(tampered)} file(s) do not match log:")
        for t in tampered:
            for line in t.splitlines():
                print(f"    {line}")

    if files_ok and not missing:
        print(f"\n  OK   all {verified} verifiable files match log")
    print()

    print("=== Result ===")
    overall = chain_ok and files_ok
    print(f"  {'PASS' if overall else 'FAIL'}")
    return overall


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify bootstrap audit chain and file integrity"
    )
    parser.add_argument(
        "--log", type=Path, default=_DEFAULT_LOG,
        help=f"Path to audit log (default: {_DEFAULT_LOG})"
    )
    args = parser.parse_args()
    sys.exit(0 if verify(args.log) else 1)
