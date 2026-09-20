"""Tests for the MCP build_feature_ensemble tool's `learn` wiring (#6)."""
from unittest.mock import MagicMock, patch

import pytest

from mcp_server.tools import ACETools


@pytest.fixture
def tools(tmp_path):
    t = ACETools(playbook_id="pb1")
    t._audit = None
    return t


def _fake_runner(result):
    runner = MagicMock()
    runner.run.return_value = result
    return patch("src.agents.ensemble_build.EnsembleBuildRunner", return_value=runner), runner


def _result(learning=None):
    from src.agents.ensemble_build import EnsembleBuildResult

    return EnsembleBuildResult(
        requirement="do a thing", language="python",
        winner_model="a/m", winner_submission_id="sub1", committed=True,
        learning=learning,
    )


def test_tool_is_registered(tools):
    names = [t["name"] for t in tools.get_tool_definitions()]
    assert "build_feature_ensemble" in names


def test_learn_defaults_to_false(tools, tmp_path):
    patcher, runner = _fake_runner(_result())
    with patcher:
        tools._handle_build_feature_ensemble({
            "project_path": str(tmp_path), "models": ["a/m", "b/m"], "feature": "do a thing",
        })
    assert runner.run.call_args.kwargs["learn"] is False


def test_learn_true_is_threaded_to_the_runner(tools, tmp_path):
    patcher, runner = _fake_runner(_result())
    with patcher:
        tools._handle_build_feature_ensemble({
            "project_path": str(tmp_path), "models": ["a/m", "b/m"], "feature": "do a thing",
            "learn": True,
        })
    assert runner.run.call_args.kwargs["learn"] is True


def test_learning_summary_is_surfaced_in_the_response(tools, tmp_path):
    learning = {"approved_bullets": 2, "bullets_added_to_playbook": 2}
    patcher, runner = _fake_runner(_result(learning=learning))
    with patcher:
        payload = tools._handle_build_feature_ensemble({
            "project_path": str(tmp_path), "models": ["a/m", "b/m"], "feature": "do a thing",
            "learn": True,
        })
    assert payload["learning"] == learning
