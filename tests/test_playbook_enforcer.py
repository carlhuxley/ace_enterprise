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

    def test_warns_when_ratio_too_high(self, tmp_path):
        """Should warn if edit:test ratio exceeds threshold."""
        from src.utils.playbook_enforcer import PlaybookEnforcer
        from src.utils.session_log import SessionLog

        log = SessionLog(log_file=tmp_path / "session.json")
        # 5 edits, 2 tests = ratio 2.5
        log.log_edit("src/a.py", "edit 1")
        log.log_test("tests/test_a.py", passed=True, count=1)
        log.log_edit("src/b.py", "edit 2")
        log.log_edit("src/c.py", "edit 3")
        log.log_edit("src/d.py", "edit 4")
        log.log_edit("src/e.py", "edit 5")
        log.log_test("tests/test_b.py", passed=True, count=1)

        enforcer = PlaybookEnforcer(session_log_path=tmp_path / "session.json", max_ratio=2.0)
        result = enforcer.check_can_edit("src/f.py")

        assert result.allowed is False
        assert "ratio" in result.reason.lower()

    def test_get_stats_returns_current_metrics(self, tmp_path):
        """Should return current edit/test metrics."""
        from src.utils.playbook_enforcer import PlaybookEnforcer
        from src.utils.session_log import SessionLog

        log = SessionLog(log_file=tmp_path / "session.json")
        log.log_edit("src/a.py", "edit 1")
        log.log_edit("src/b.py", "edit 2")
        log.log_test("tests/test_a.py", passed=True, count=5)

        enforcer = PlaybookEnforcer(session_log_path=tmp_path / "session.json")
        stats = enforcer.get_stats()

        assert stats["edits"] == 2
        assert stats["tests"] == 1
        assert stats["ratio"] == 2.0
