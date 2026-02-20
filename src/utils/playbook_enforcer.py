"""PlaybookEnforcer - enforces high-frequency feedback rules."""
import json
from dataclasses import dataclass
from pathlib import Path

from src.utils.session_log import SessionLog


@dataclass
class EditCheckResult:
    """Result of checking if an edit is allowed."""
    allowed: bool
    reason: str


class PlaybookEnforcer:
    """Enforces playbook rules like ace-006 (high-frequency feedback)."""

    def __init__(self, session_log_path: Path | None = None, max_ratio: float = 2.0):
        self.session_log_path = session_log_path or Path(".session_log.json")
        self.max_ratio = max_ratio
        self._session_log = SessionLog(log_file=self.session_log_path)

    def check_can_edit(self, file_path: str) -> EditCheckResult:
        """Check if an edit is allowed based on playbook rules."""
        # Load session log
        if not self.session_log_path.exists():
            self._session_log.log_edit(file_path, "auto-logged by enforcer")
            return EditCheckResult(allowed=True, reason="No session log, first edit allowed")

        entries = json.loads(self.session_log_path.read_text())
        if not entries:
            self._session_log.log_edit(file_path, "auto-logged by enforcer")
            return EditCheckResult(allowed=True, reason="Empty session log, first edit allowed")

        # Check ratio of edits to tests
        edits = sum(1 for e in entries if e.get("type") == "edit")
        tests = sum(1 for e in entries if e.get("type") == "test")
        if tests > 0:
            ratio = edits / tests
            if ratio > self.max_ratio:
                return EditCheckResult(
                    allowed=False,
                    reason=f"Ratio too high: {ratio:.1f} edits/test (max: {self.max_ratio}) - run more tests (ace-006)"
                )

        # Check if last entry was an untested edit
        last_entry = entries[-1]
        if last_entry.get("type") == "edit":
            return EditCheckResult(
                allowed=False,
                reason=f"Untested edit: {last_entry.get('file')} - run tests first (ace-006)"
            )

        # All checks passed - log the edit and allow
        self._session_log.log_edit(file_path, "auto-logged by enforcer")
        return EditCheckResult(allowed=True, reason="Previous edit was tested")

    def get_stats(self) -> dict:
        """Get current session metrics."""
        if not self.session_log_path.exists():
            return {"edits": 0, "tests": 0, "ratio": 0.0}

        entries = json.loads(self.session_log_path.read_text())
        edits = sum(1 for e in entries if e.get("type") == "edit")
        tests = sum(1 for e in entries if e.get("type") == "test")
        ratio = edits / tests if tests > 0 else 0.0

        return {"edits": edits, "tests": tests, "ratio": ratio}
