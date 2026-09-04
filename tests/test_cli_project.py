"""Tests for `ace project` (src/cli/main.py::cmd_project).

ProjectArchitect / ProjectBuilder / the LLM client are patched -- these check
cmd_project's own control flow.
"""
import argparse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.cli.main import _build_parser, cmd_project
from src.contracts.project_architect import ModuleSpec, ProjectPlan


def _args(**overrides):
    defaults = {
        "spec": None,
        "project": Path("."),
        "model": None,
        "plan_only": False,
        "yes": True,
        "resume": False,
        "keep_going": False,
        "verbose": False,
        "playbook_id": None,
        "no_learn": True,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    spec = tmp_path / "app.spec"
    spec.write_text("build a todo app")
    return tmp_path, spec


def _plan():
    return ProjectPlan(
        spec="build a todo app",
        modules=[
            ModuleSpec("store", "persistence"),
            ModuleSpec("api", "http layer", depends_on=("store",)),
        ],
    )


def _patch_deps(plan=None, plan_ok=True, build_result=None):
    plan = plan or _plan()
    architect = MagicMock()
    architect.plan.return_value = SimpleNamespace(
        success=plan_ok, plan=plan if plan_ok else None, error=None if plan_ok else "bad spec",
    )
    builder = MagicMock()
    builder.build.return_value = build_result or SimpleNamespace(
        outcomes=[
            SimpleNamespace(name="store", status=_S("built"), cycles=1, error=None),
            SimpleNamespace(name="api", status=_S("built"), cycles=2, error=None),
        ],
        assembly_passed=True,
        assembly_failures=[],
        success=True,
    )
    return (
        patch("src.contracts.project_architect.ProjectArchitect", return_value=architect),
        patch("src.cli.project_builder.ProjectBuilder", return_value=builder),
        patch("src.cli.factory.default_llm_client", return_value=SimpleNamespace(provider="ollama", model="q")),
        architect,
        builder,
    )


class _S(str):
    """Tiny stand-in for ModuleStatus (has .value)."""
    @property
    def value(self):
        return str(self)


class TestErrorPaths:
    def test_missing_spec_file(self, tmp_path, capsys):
        rc = cmd_project(_args(spec=tmp_path / "nope.spec", project=tmp_path))
        assert rc == 1
        assert "spec file not found" in capsys.readouterr().err

    def test_missing_project_dir(self, project, capsys):
        _, spec = project
        rc = cmd_project(_args(spec=spec, project=Path("/does/not/exist")))
        assert rc == 1
        assert "project directory not found" in capsys.readouterr().err

    def test_planning_failure_returns_1(self, project, capsys):
        root, spec = project
        pa, pb, pl, *_ = _patch_deps(plan_ok=False)
        with pa, pb, pl:
            rc = cmd_project(_args(spec=spec, project=root))
        assert rc == 1
        assert "could not plan" in capsys.readouterr().err


class TestPlanOnly:
    def test_plan_only_prints_dag_and_does_not_build(self, project, capsys):
        root, spec = project
        pa, pb, pl, architect, builder = _patch_deps()
        with pa, pb, pl:
            rc = cmd_project(_args(spec=spec, project=root, plan_only=True))
        assert rc == 0
        builder.build.assert_not_called()
        out = capsys.readouterr().out
        assert "store" in out and "api" in out


class TestBuild:
    def test_builds_and_reports(self, project, capsys):
        root, spec = project
        pa, pb, pl, architect, builder = _patch_deps()
        with pa, pb, pl:
            rc = cmd_project(_args(spec=spec, project=root))
        assert rc == 0
        builder.build.assert_called_once()
        _, kwargs = builder.build.call_args
        assert kwargs["stop_on_failure"] is True
        assert kwargs["resume"] is False

    def test_keep_going_flips_stop_on_failure(self, project):
        root, spec = project
        pa, pb, pl, architect, builder = _patch_deps()
        with pa, pb, pl:
            cmd_project(_args(spec=spec, project=root, keep_going=True))
        _, kwargs = builder.build.call_args
        assert kwargs["stop_on_failure"] is False

    def test_declining_the_prompt_aborts(self, project, capsys):
        root, spec = project
        pa, pb, pl, architect, builder = _patch_deps()
        with pa, pb, pl, patch("src.cli.main._confirm", return_value=False):
            rc = cmd_project(_args(spec=spec, project=root, yes=False))
        assert rc == 1
        builder.build.assert_not_called()
        assert "aborted" in capsys.readouterr().out

    def test_unsuccessful_build_returns_1(self, project):
        root, spec = project
        bad = SimpleNamespace(outcomes=[], assembly_passed=False, assembly_failures=["x"], success=False)
        pa, pb, pl, architect, builder = _patch_deps(build_result=bad)
        with pa, pb, pl:
            rc = cmd_project(_args(spec=spec, project=root))
        assert rc == 1


class TestModelOverride:
    def test_model_flag_builds_client_from_ref(self, project):
        root, spec = project
        pa, pb, pl, architect, builder = _patch_deps()
        with pa, pb, patch(
            "src.cli.factory.llm_client_from_ref",
            return_value=SimpleNamespace(provider="openrouter", model="qwen/qwen3-coder"),
        ) as from_ref:
            cmd_project(_args(spec=spec, project=root, model="openrouter/qwen/qwen3-coder"))
        from_ref.assert_called_once_with("openrouter/qwen/qwen3-coder")

    def test_bad_model_ref_rejected(self, project, capsys):
        root, spec = project
        rc = cmd_project(_args(spec=spec, project=root, model="justqwen"))
        assert rc == 1
        assert "<provider>/<model>" in capsys.readouterr().err


def test_parser_wires_project_subcommand():
    ns = _build_parser().parse_args(
        ["project", "s.spec", "--plan-only", "-y", "--resume", "--model", "ollama/q:7b"]
    )
    assert ns.command == "project"
    assert ns.plan_only and ns.yes and ns.resume
    assert ns.model == "ollama/q:7b"
