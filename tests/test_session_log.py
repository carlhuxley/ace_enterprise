"""Tests for SessionLog - tracks edits and tests in current session."""
import pytest
from pathlib import Path


class TestSessionLog:
    """Test session logging functionality."""

    def test_can_create_session_log(self, tmp_path):
        """Session log can be created."""
        from src.utils.session_log import SessionLog

        log = SessionLog(log_file=tmp_path / "session.json")
        assert log is not None

    def test_can_log_edit(self, tmp_path):
        """Can log a file edit."""
        from src.utils.session_log import SessionLog

        log = SessionLog(log_file=tmp_path / "session.json")
        log.log_edit("src/foo.py", "Added function bar")

        entries = log.get_entries()
        assert len(entries) == 1
        assert entries[0]["type"] == "edit"
        assert entries[0]["file"] == "src/foo.py"

    def test_can_log_test_run(self, tmp_path):
        """Can log a test run."""
        from src.utils.session_log import SessionLog

        log = SessionLog(log_file=tmp_path / "session.json")
        log.log_test("tests/test_foo.py", passed=True, count=5)

        entries = log.get_entries()
        assert len(entries) == 1
        assert entries[0]["type"] == "test"
        assert entries[0]["passed"] is True

    def test_get_summary(self, tmp_path):
        """Can get summary stats."""
        from src.utils.session_log import SessionLog

        log = SessionLog(log_file=tmp_path / "session.json")
        log.log_edit("a.py", "edit 1")
        log.log_edit("b.py", "edit 2")
        log.log_test("test_a.py", passed=True, count=3)

        summary = log.get_summary()
        assert summary["edits"] == 2
        assert summary["tests_run"] == 1
        assert summary["tests_passed"] == 1
