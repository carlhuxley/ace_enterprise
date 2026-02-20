"""PlaybookEnforcer - enforces high-frequency feedback rules."""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EditCheckResult:
    """Result of checking if an edit is allowed."""
    allowed: bool
    reason: str


class PlaybookEnforcer:
    """Enforces playbook rules like ace-006 (high-frequency feedback)."""

    def __init__(self, session_log_path: Path | None = None):
        self.session_log_path = session_log_path or Path(".session_log.json")

    def check_can_edit(self, file_path: str) -> EditCheckResult:
        """Check if an edit is allowed based on playbook rules."""
        # Load session log
        if not self.session_log_path.exists():
            return EditCheckResult(allowed=True, reason="No session log, first edit allowed")

        entries = json.loads(self.session_log_path.read_text())
        if not entries:
            return EditCheckResult(allowed=True, reason="Empty session log, first edit allowed")

        # Check if last entry was an untested edit
        last_entry = entries[-1]
        if last_entry.get("type") == "edit":
            return EditCheckResult(
                allowed=False,
                reason=f"Untested edit: {last_entry.get('file')} - run tests first (ace-006)"
            )

        return EditCheckResult(allowed=True, reason="Previous edit was tested")
