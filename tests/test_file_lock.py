import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from src.utils.file_lock import (
    DriftDetector,
    DriftReport,
    FileDrift,
    FileLockContext,
    InadvertentDriftError,
)


@pytest.fixture
def project(tmp_path):
    """A small project tree: src/a.py, src/b.py, tests/test_a.py."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "a.py").write_text("def alpha(): pass\n")
    (tmp_path / "src" / "b.py").write_text("def beta(): pass\n")
    (tmp_path / "tests" / "test_a.py").write_text("def test_alpha(): pass\n")
    return tmp_path


@pytest.fixture
def git_project(project):
    """project fixture with a git repo and initial commit."""
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=project, check=True, capture_output=True)
    return project


class TestFileLockContext:
    def test_non_target_files_become_read_only(self, project):
        target = [project / "src" / "a.py"]
        non_target = project / "src" / "b.py"

        with FileLockContext(target, project):
            mode = non_target.stat().st_mode
            assert not (mode & 0o200), "non-target file should not be writable"

    def test_target_files_remain_writable(self, project):
        target = [project / "src" / "a.py"]

        with FileLockContext(target, project):
            mode = (project / "src" / "a.py").stat().st_mode
            assert mode & 0o200, "target file should remain writable"

    def test_permissions_restored_on_exit(self, project):
        non_target = project / "src" / "b.py"
        original_mode = non_target.stat().st_mode

        with FileLockContext([project / "src" / "a.py"], project):
            pass

        assert non_target.stat().st_mode == original_mode

    def test_permissions_restored_on_exception(self, project):
        non_target = project / "src" / "b.py"
        original_mode = non_target.stat().st_mode

        try:
            with FileLockContext([project / "src" / "a.py"], project):
                raise RuntimeError("boom")
        except RuntimeError:
            pass

        assert non_target.stat().st_mode == original_mode

    def test_write_to_locked_file_raises(self, project):
        target = [project / "src" / "a.py"]
        non_target = project / "src" / "b.py"

        with FileLockContext(target, project):
            with pytest.raises(PermissionError):
                non_target.write_text("oops\n")

    def test_pycache_files_are_skipped(self, project):
        pycache = project / "src" / "__pycache__"
        pycache.mkdir()
        cached = pycache / "a.cpython-312.pyc"
        cached.write_bytes(b"fake bytecode")
        original_mode = cached.stat().st_mode

        with FileLockContext([project / "src" / "a.py"], project):
            assert cached.stat().st_mode == original_mode

    def test_symlinks_are_skipped(self, project):
        # File truly outside the project root — linked in.
        # We must not chmod through the symlink and affect external files.
        import tempfile
        with tempfile.TemporaryDirectory() as ext_dir:
            external = Path(ext_dir) / "external.py"
            external.write_text("x = 1\n")
            link = project / "src" / "link.py"
            link.symlink_to(external)
            original_mode = external.stat().st_mode

            with FileLockContext([project / "src" / "a.py"], project):
                assert external.stat().st_mode == original_mode

    def test_context_manager_returns_self(self, project):
        ctx = FileLockContext([project / "src" / "a.py"], project)
        with ctx as result:
            assert result is ctx


class TestDriftDetector:
    def test_clean_project_returns_empty_report(self, git_project):
        detector = DriftDetector(git_project)
        report = detector.check([git_project / "src" / "a.py"])
        assert report.is_clean

    def test_change_to_non_target_detected(self, git_project):
        (git_project / "src" / "b.py").write_text("def beta(): return 42\n")
        detector = DriftDetector(git_project)
        report = detector.check([git_project / "src" / "a.py"])
        assert not report.is_clean
        drifted_paths = {d.file_path for d in report.drifted_files}
        assert git_project / "src" / "b.py" in drifted_paths

    def test_change_to_target_not_reported(self, git_project):
        (git_project / "src" / "a.py").write_text("def alpha(): return 1\n")
        detector = DriftDetector(git_project)
        report = detector.check([git_project / "src" / "a.py"])
        assert report.is_clean

    def test_drift_report_contains_line_counts(self, git_project):
        (git_project / "src" / "b.py").write_text("def beta(): return 42\ndef extra(): pass\n")
        detector = DriftDetector(git_project)
        report = detector.check([git_project / "src" / "a.py"])
        drift = report.drifted_files[0]
        assert drift.added_lines >= 1
        assert drift.diff_snippet != ""

    def test_multiple_drifted_files(self, git_project):
        (git_project / "src" / "b.py").write_text("changed\n")
        (git_project / "tests" / "test_a.py").write_text("changed too\n")
        detector = DriftDetector(git_project)
        report = detector.check([git_project / "src" / "a.py"])
        assert len(report.drifted_files) == 2


class TestDriftReport:
    def test_assert_clean_raises_on_drift(self):
        drift = FileDrift(
            file_path=Path("src/b.py"),
            added_lines=1,
            removed_lines=0,
            diff_snippet="+oops",
        )
        report = DriftReport(drifted_files=[drift])
        with pytest.raises(InadvertentDriftError) as exc_info:
            report.assert_clean()
        assert "src/b.py" in str(exc_info.value)

    def test_assert_clean_passes_on_empty(self):
        DriftReport(drifted_files=[]).assert_clean()

    def test_is_clean_property(self):
        assert DriftReport(drifted_files=[]).is_clean
        assert not DriftReport(drifted_files=[
            FileDrift(Path("x.py"), 1, 0, "")
        ]).is_clean

    def test_inadvertent_drift_error_carries_report(self):
        drift = FileDrift(Path("src/b.py"), 2, 1, "diff")
        report = DriftReport(drifted_files=[drift])
        err = InadvertentDriftError(report)
        assert err.report is report
