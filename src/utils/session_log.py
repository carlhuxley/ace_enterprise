"""Session log - tracks edits and tests in current session."""
import json
from datetime import datetime
from pathlib import Path


class SessionLog:
    """Simple session tracker for dogfooding loop visibility."""

    def __init__(self, log_file: Path | None = None):
        self.log_file = log_file or Path(".session_log.json")
        self._entries: list[dict] = []

    def log_edit(self, file: str, description: str) -> None:
        """Log a file edit."""
        self._entries.append({
            "type": "edit",
            "file": file,
            "description": description,
            "timestamp": datetime.now().isoformat()
        })
        self._save()

    def log_test(self, test_file: str, passed: bool, count: int) -> None:
        """Log a test run."""
        self._entries.append({
            "type": "test",
            "file": test_file,
            "passed": passed,
            "count": count,
            "timestamp": datetime.now().isoformat()
        })
        self._save()

    def get_entries(self) -> list[dict]:
        """Get all log entries."""
        return self._entries

    def get_summary(self) -> dict:
        """Get summary stats."""
        edits = sum(1 for e in self._entries if e["type"] == "edit")
        tests = [e for e in self._entries if e["type"] == "test"]
        return {
            "edits": edits,
            "tests_run": len(tests),
            "tests_passed": sum(1 for t in tests if t["passed"])
        }

    def _save(self) -> None:
        """Persist to file."""
        self.log_file.write_text(json.dumps(self._entries, indent=2))
