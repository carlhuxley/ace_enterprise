"""Tests for `ace view` (src/cli/main.py::cmd_view).

resolve_attempt / render_attempt_video / summarize_telemetry are patched
throughout -- no real pybullet or video encoding here.
"""
import argparse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.cli.main import cmd_view


def _args(**overrides):
    defaults = {
        "attempt": Path("attempt.py"),
        "video": False,
        "output": None,
        "scenario": None,
        "max_steps": None,
        "verbose": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _record(**overrides):
    defaults = {
        "controller_path": Path("attempts/controller_cycle1_green_attempt1.py"),
        "scenario_name": "tactile",
        "telemetry": None,
        "invariants": [],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestErrorPaths:
    def test_missing_attempt_file_returns_1(self, capsys):
        with patch(
            "src.agents.simulation_replay.resolve_attempt",
            side_effect=FileNotFoundError("no archived attempt at attempt.py"),
        ):
            rc = cmd_view(_args())
        assert rc == 1
        assert "no archived attempt" in capsys.readouterr().err

    def test_unknown_scenario_override_returns_1(self, capsys):
        with patch(
            "src.agents.simulation_replay.resolve_attempt",
            side_effect=ValueError("unknown scenario 'bogus'"),
        ):
            rc = cmd_view(_args(scenario="bogus"))
        assert rc == 1
        assert "unknown scenario" in capsys.readouterr().err


class TestSuccessPath:
    def test_no_telemetry_prints_a_clear_note_not_an_error(self, capsys):
        with patch("src.agents.simulation_replay.resolve_attempt", return_value=_record()):
            rc = cmd_view(_args())
        assert rc == 0
        out = capsys.readouterr().out
        assert "No telemetry recorded" in out

    def test_telemetry_present_prints_the_summary(self, capsys):
        record = _record(telemetry=object(), invariants=[object()])
        with patch("src.agents.simulation_replay.resolve_attempt", return_value=record), \
             patch("src.agents.simulation_runner.summarize_telemetry", return_value="CONVERGED after 229 steps"):
            rc = cmd_view(_args())
        assert rc == 0
        assert "CONVERGED after 229 steps" in capsys.readouterr().out

    def test_video_flag_renders_and_prints_output_path(self, capsys):
        record = _record()
        with patch("src.agents.simulation_replay.resolve_attempt", return_value=record), \
             patch("src.agents.simulation_replay.render_attempt_video") as render:
            rc = cmd_view(_args(video=True))
        assert rc == 0
        render.assert_called_once()
        assert str(record.controller_path.with_suffix(".mp4")) in capsys.readouterr().out

    def test_video_output_override_is_passed_through(self, capsys):
        record = _record()
        custom_output = Path("/tmp/custom.mp4")
        with patch("src.agents.simulation_replay.resolve_attempt", return_value=record), \
             patch("src.agents.simulation_replay.render_attempt_video") as render:
            cmd_view(_args(video=True, output=custom_output))
        assert render.call_args[0][1] == custom_output

    def test_video_missing_optional_dependency_returns_1(self, capsys):
        record = _record()
        with patch("src.agents.simulation_replay.resolve_attempt", return_value=record), \
             patch(
                 "src.agents.simulation_replay.render_attempt_video",
                 side_effect=ImportError("No module named 'imageio'"),
             ):
            rc = cmd_view(_args(video=True))
        assert rc == 1
        assert "simulation' extra" in capsys.readouterr().err

    def test_max_steps_is_passed_through_to_render(self):
        record = _record()
        with patch("src.agents.simulation_replay.resolve_attempt", return_value=record), \
             patch("src.agents.simulation_replay.render_attempt_video") as render:
            cmd_view(_args(video=True, max_steps=40))
        assert render.call_args.kwargs["max_steps"] == 40
