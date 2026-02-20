"""Tests for PlaybookEnforcer - enforces high-frequency feedback rules."""
import pytest
from pathlib import Path


class TestPlaybookEnforcer:
    """Test playbook enforcement mechanism."""

    def test_allows_first_edit(self, tmp_path):
        """First edit should always be allowed."""
        from src.utils.playbook_enforcer import PlaybookEnforcer

        enforcer = PlaybookEnforcer(session_log_path=tmp_path / "session.json")

        result = enforcer.check_can_edit("src/foo.py")

        assert result.allowed is True

    def test_warns_after_untested_edit(self, tmp_path):
        """Should warn if previous edit wasn't tested."""
        from src.utils.playbook_enforcer import PlaybookEnforcer
        from src.utils.session_log import SessionLog

        # Create session with one untested edit
        log = SessionLog(log_file=tmp_path / "session.json")
        log.log_edit("src/foo.py", "First edit")

        enforcer = PlaybookEnforcer(session_log_path=tmp_path / "session.json")
        result = enforcer.check_can_edit("src/bar.py")

        assert result.allowed is False
        assert "untested" in result.reason.lower()

    def test_allows_edit_after_test(self, tmp_path):
        """Should allow edit if previous edit was tested."""
        from src.utils.playbook_enforcer import PlaybookEnforcer
        from src.utils.session_log import SessionLog

        log = SessionLog(log_file=tmp_path / "session.json")
        log.log_edit("src/foo.py", "First edit")
        log.log_test("tests/test_foo.py", passed=True, count=1)

        enforcer = PlaybookEnforcer(session_log_path=tmp_path / "session.json")
        result = enforcer.check_can_edit("src/bar.py")

        assert result.allowed is True
