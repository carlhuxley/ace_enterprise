"""Tests for `ace tdd` (src/cli/main.py::cmd_tdd).

build_agent() is patched throughout -- these tests check cmd_tdd's own
control flow (path resolution, error handling, handle lifecycle), not the
sandboxed engine itself (covered by tests/test_cli_factory.py).
"""
import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.cli.main import cmd_tdd


def _args(**overrides):
    defaults = dict(
        project=Path("."),
        feature=None,
        requirement=None,
        playbook_id=None,
        max_iterations=None,
        no_learn=False,
        verbose=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "features").mkdir()
    feature = tmp_path / "features" / "login.feature"
    feature.write_text("Feature: User login\n\n  Scenario: ok\n    Given a user\n")
    return tmp_path


def _stub_handle(success=True, iterations=2):
    handle = MagicMock()
    handle.build_from_feature.return_value = MagicMock(success=success, iterations=iterations)
    handle.file_paths_for.return_value = (Path("tests/test_login.py"), Path("src/login.py"))
    return handle


class TestErrorPaths:
    def test_missing_project_dir_returns_1(self, tmp_path, capsys):
        rc = cmd_tdd(_args(project=tmp_path / "does_not_exist"))
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_no_feature_files_returns_1(self, tmp_path, capsys):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        rc = cmd_tdd(_args(project=tmp_path))
        assert rc == 1
        assert "no .feature files found" in capsys.readouterr().err

    def test_explicit_missing_feature_file_returns_1(self, project, capsys):
        rc = cmd_tdd(_args(project=project, feature=Path("nope.feature")))
        assert rc == 1
        assert "feature file not found" in capsys.readouterr().err


class TestSuccessPath:
    def test_builds_from_discovered_feature(self, project):
        with patch("src.cli.factory.build_agent", return_value=_stub_handle()) as build_agent:
            rc = cmd_tdd(_args(project=project))
        assert rc == 0
        build_agent.assert_called_once()
        _, kwargs = build_agent.call_args
        assert kwargs["skip_learn"] is False

    def test_no_learn_flag_forwarded(self, project):
        with patch("src.cli.factory.build_agent", return_value=_stub_handle()) as build_agent:
            cmd_tdd(_args(project=project, no_learn=True))
        _, kwargs = build_agent.call_args
        assert kwargs["skip_learn"] is True

    def test_requirement_override_forwarded_to_handle(self, project):
        handle = _stub_handle()
        with patch("src.cli.factory.build_agent", return_value=handle):
            cmd_tdd(_args(project=project, requirement="custom text"))
        _, kwargs = handle.build_from_feature.call_args
        assert kwargs["requirement"] == "custom text"

    def test_incomplete_result_returns_1(self, project):
        with patch("src.cli.factory.build_agent", return_value=_stub_handle(success=False)):
            rc = cmd_tdd(_args(project=project))
        assert rc == 1

    def test_handle_is_stopped_after_success(self, project):
        handle = _stub_handle()
        with patch("src.cli.factory.build_agent", return_value=handle):
            cmd_tdd(_args(project=project))
        handle.stop.assert_called_once()

    def test_handle_is_stopped_even_if_build_raises(self, project):
        handle = _stub_handle()
        handle.build_from_feature.side_effect = RuntimeError("container boom")
        with patch("src.cli.factory.build_agent", return_value=handle):
            with pytest.raises(RuntimeError):
                cmd_tdd(_args(project=project))
        handle.stop.assert_called_once()

    def test_explicit_feature_path_relative_to_project(self, project):
        with patch("src.cli.factory.build_agent", return_value=_stub_handle()) as build_agent:
            rc = cmd_tdd(_args(project=project, feature=Path("features/login.feature")))
        assert rc == 0
        build_agent.assert_called_once()
