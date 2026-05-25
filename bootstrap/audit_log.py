"""Tamper-evident append-only audit log for the bootstrap pipeline.

Each record includes a chain_hash — SHA-256 of (prev_hash + sorted JSON of the
entry). An auditor can replay the file and verify no record was modified or
inserted after the fact.
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_TZ_UK = ZoneInfo("Europe/London")


class BootstrapAuditLog:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._prev_hash = "0" * 64
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    self._prev_hash = json.loads(line).get("chain_hash", self._prev_hash)
                except (json.JSONDecodeError, KeyError):
                    pass

    def record(self, event: str, **fields) -> str:
        entry = {"ts": datetime.now(_TZ_UK).isoformat(), "event": event, **fields}
        entry["chain_hash"] = hashlib.sha256(
            (self._prev_hash + json.dumps(entry, sort_keys=True)).encode()
        ).hexdigest()
        self._prev_hash = entry["chain_hash"]
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry["chain_hash"]

    @staticmethod
    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def sha256_str(s: str) -> str:
        return hashlib.sha256(s.encode()).hexdigest()

    def verify_chain(self) -> tuple[bool, str]:
        """Re-derive chain hashes from disk and confirm they match recorded values.

        Returns (True, "") on success or (False, first_mismatch_entry) on failure.
        """
        prev = "0" * 64
        for line in self._path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            recorded = entry.pop("chain_hash")
            expected = hashlib.sha256(
                (prev + json.dumps(entry, sort_keys=True)).encode()
            ).hexdigest()
            if recorded != expected:
                return False, json.dumps(entry)
            prev = recorded
        return True, ""
