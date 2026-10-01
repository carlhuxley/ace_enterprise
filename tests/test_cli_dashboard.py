"""Tests for `ace dashboard` (src/cli/main.py::cmd_dashboard)."""
import argparse
import builtins
from pathlib import Path
from unittest.mock import patch

from src.cli.main import cmd_dashboard


def _args(**overrides):
    defaults = {"project": Path("."), "verbose": False}
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestErrorPaths:
    def test_missing_project_dir_returns_1(self, tmp_path, capsys):
        rc = cmd_dashboard(_args(project=tmp_path / "does_not_exist"))
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_missing_dashboard_extra_reports_a_clear_error(self, tmp_path, capsys):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "src.ui.dashboard":
                raise ImportError("No module named 'textual'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            rc = cmd_dashboard(_args(project=tmp_path))
        assert rc == 1
        err = capsys.readouterr().err
        assert "dashboard' extra" in err
        assert "pip install -e .[dashboard]" in err


class TestSuccessPath:
    def test_resolves_project_and_calls_run_dashboard(self, tmp_path):
        with patch("src.ui.dashboard.run_dashboard", return_value=0) as mock_run:
            rc = cmd_dashboard(_args(project=tmp_path))
        assert rc == 0
        mock_run.assert_called_once_with(project_root=tmp_path.resolve())

    def test_propagates_run_dashboard_exit_code(self, tmp_path):
        with patch("src.ui.dashboard.run_dashboard", return_value=1):
            rc = cmd_dashboard(_args(project=tmp_path))
        assert rc == 1


class TestArgparseWiring:
    def test_dashboard_subcommand_parses_with_defaults(self):
        from src.cli.main import _build_parser

        args = _build_parser().parse_args(["dashboard"])
        assert args.command == "dashboard"
        assert args.project == Path(".")

    def test_dashboard_subcommand_accepts_project_override(self):
        from src.cli.main import _build_parser

        args = _build_parser().parse_args(["dashboard", "--project", "/tmp/x"])
        assert args.project == Path("/tmp/x")

    def test_tdd_watch_flag_defaults_to_false(self):
        from src.cli.main import _build_parser

        args = _build_parser().parse_args(["tdd"])
        assert args.watch is False

    def test_tdd_watch_flag_can_be_set(self):
        from src.cli.main import _build_parser

        args = _build_parser().parse_args(["tdd", "--watch"])
        assert args.watch is True

    def test_main_dispatches_dashboard_command(self):
        import sys

        from src.cli.main import main

        with patch.object(sys, "argv", ["ace", "dashboard", "--project", "/tmp/x"]), \
             patch("src.cli.main.cmd_dashboard", return_value=0) as mock_cmd, \
             patch("sys.exit") as mock_exit:
            main()
        mock_cmd.assert_called_once()
        mock_exit.assert_called_once_with(0)
