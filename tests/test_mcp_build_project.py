"""Tests for the MCP build_project tool (mcp_server/tools.py)."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from mcp_server.tools import ACETools
from src.audit.local_client import LocalAuditClient
from src.contracts.project_architect import ModuleSpec, ProjectPlan


@pytest.fixture
def tools(tmp_path):
    t = ACETools(playbook_id="pb1")
    t._audit = LocalAuditClient(database_url=f"sqlite:///{tmp_path}/audit.db")
    return t


def _plan():
    return ProjectPlan(spec="s", modules=[
        ModuleSpec("store", "persistence"),
        ModuleSpec("api", "routes", depends_on=("store",)),
    ])


def _patched(plan_ok=True):
    architect = MagicMock()
    architect.plan.return_value = SimpleNamespace(
        success=plan_ok, plan=_plan() if plan_ok else None, error=None if plan_ok else "nope",
    )
    builder = MagicMock()
    builder.build.return_value = SimpleNamespace(
        success=True,
        to_payload=lambda: {"modules": [{"name": "store", "status": "built"}], "assembly_passed": True},
    )
    return (
        patch("src.contracts.project_architect.ProjectArchitect", return_value=architect),
        patch("src.cli.project_builder.ProjectBuilder", return_value=builder),
        architect,
        builder,
    )


def test_tool_is_registered(tools):
    assert "build_project" in [t["name"] for t in tools.get_tool_definitions()]


def test_requires_spec_or_spec_file(tools, tmp_path):
    result = tools._handle_build_project({"project_path": str(tmp_path)})
    assert result["success"] is False
    assert "spec" in result["error"]


def test_plan_only_returns_plan_without_building(tools, tmp_path):
    pa, pb, architect, builder = _patched()
    with pa, pb:
        result = tools._handle_build_project({
            "project_path": str(tmp_path), "spec": "build a todo app", "plan_only": True,
        })
    assert result["success"] is True
    assert result["plan_only"] is True
    assert result["plan"]["build_order"] == ["store", "api"]
    builder.build.assert_not_called()


def test_full_build_returns_plan_and_outcomes(tools, tmp_path):
    pa, pb, architect, builder = _patched()
    with pa, pb:
        result = tools._handle_build_project({
            "project_path": str(tmp_path), "spec": "build a todo app",
        })
    assert result["success"] is True
    assert result["sandboxed"] is True
    assert result["plan"]["build_order"] == ["store", "api"]
    assert result["assembly_passed"] is True
    _, kwargs = builder.build.call_args
    assert kwargs["stop_on_failure"] is True


def test_planning_failure_is_reported(tools, tmp_path):
    pa, pb, architect, builder = _patched(plan_ok=False)
    with pa, pb:
        result = tools._handle_build_project({
            "project_path": str(tmp_path), "spec": "???",
        })
    assert result["success"] is False
    assert "planning failed" in result["error"]
