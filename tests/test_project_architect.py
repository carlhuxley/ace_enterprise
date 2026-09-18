"""Tests for src/contracts/project_architect.py.

The LLM boundary is `ProjectArchitect._generate_plan` -- patched throughout,
so no network / model call happens.
"""
from unittest.mock import patch

import pytest

from src.contracts.project_architect import (
    ModuleSpec,
    ProjectArchitect,
    ProjectPlan,
    ProjectPlanError,
)


def _architect():
    return ProjectArchitect(llm_client=object(), model_id="test-model")


def _plan_with(modules: list[dict]):
    with patch.object(ProjectArchitect, "_generate_plan", return_value=modules):
        return _architect().plan("build a thing")


# --- ProjectPlan validation -------------------------------------------------

class TestProjectPlan:
    def test_build_order_is_topological_with_lexical_tiebreak(self):
        plan = ProjectPlan(
            spec="x",
            modules=[
                ModuleSpec("api", "http layer", depends_on=("auth", "db")),
                ModuleSpec("auth", "sessions", depends_on=("db",)),
                ModuleSpec("db", "storage"),
            ],
        )
        assert plan.build_order == ["db", "auth", "api"]

    def test_no_modules_rejected(self):
        with pytest.raises(ProjectPlanError, match="no modules"):
            ProjectPlan(spec="x", modules=[])

    def test_duplicate_names_rejected(self):
        with pytest.raises(ProjectPlanError, match="duplicate"):
            ProjectPlan(spec="x", modules=[ModuleSpec("a", "1"), ModuleSpec("a", "2")])

    def test_non_snake_case_name_rejected(self):
        with pytest.raises(ProjectPlanError, match="snake_case"):
            ProjectPlan(spec="x", modules=[ModuleSpec("MyModule", "d")])

    def test_unknown_dependency_rejected(self):
        with pytest.raises(ProjectPlanError, match="unknown node 'ghost'"):
            ProjectPlan(spec="x", modules=[ModuleSpec("a", "d", depends_on=("ghost",))])

    def test_cycle_rejected(self):
        with pytest.raises(ProjectPlanError, match="cycle"):
            ProjectPlan(
                spec="x",
                modules=[
                    ModuleSpec("a", "d", depends_on=("b",)),
                    ModuleSpec("b", "d", depends_on=("a",)),
                ],
            )

    def test_render_lists_modules_in_build_order(self):
        plan = ProjectPlan(
            spec="x",
            modules=[
                ModuleSpec("auth", "sessions", depends_on=("db",)),
                ModuleSpec("db", "storage"),
            ],
        )
        rendered = plan.render()
        assert rendered.index("db") < rendered.index("auth")
        assert "← db" in rendered

    def test_to_payload_is_json_safe(self):
        import json

        plan = ProjectPlan(
            spec="x", modules=[ModuleSpec("db", "storage"), ModuleSpec("api", "x", depends_on=("db",))]
        )
        json.dumps(plan.to_payload())


# --- ProjectPlan.from_spec_dir (issue #57) ---------------------------------

def _write_contract(path, module: str, depends_on: list | None = None, description: str = "", extra: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"module: {module}"]
    if depends_on is not None:
        lines.append("depends_on: [" + ", ".join(depends_on) + "]")
    if description:
        lines.append(f"description: {description}")
    lines.append(extra)
    path.write_text("\n".join(lines) + "\n")


class TestFromSpecDir:
    def test_happy_path_builds_the_same_plan_shape_as_the_llm_path(self, tmp_path):
        _write_contract(
            tmp_path / "contracts" / "db.contract.yml", "db", depends_on=[], description="storage layer"
        )
        _write_contract(
            tmp_path / "contracts" / "api.contract.yml", "api", depends_on=["db"], description="http layer"
        )
        plan = ProjectPlan.from_spec_dir(tmp_path)
        assert plan.build_order == ["db", "api"]
        by_name = {m.name: m for m in plan.modules}
        assert by_name["api"].description == "http layer"
        assert by_name["api"].depends_on == ("db",)

    def test_falls_back_to_the_dir_itself_when_no_contracts_subdir(self, tmp_path):
        _write_contract(tmp_path / "db.contract.yml", "db")
        plan = ProjectPlan.from_spec_dir(tmp_path)
        assert plan.build_order == ["db"]

    def test_prefers_contracts_subdir_over_top_level_files(self, tmp_path):
        _write_contract(tmp_path / "db.contract.yml", "wrong_module")
        _write_contract(tmp_path / "contracts" / "db.contract.yml", "right_module")
        plan = ProjectPlan.from_spec_dir(tmp_path)
        assert plan.build_order == ["right_module"]

    def test_no_contract_files_raises(self, tmp_path):
        with pytest.raises(ProjectPlanError, match="no \\*.contract.yml files"):
            ProjectPlan.from_spec_dir(tmp_path)

    def test_missing_module_key_raises(self, tmp_path):
        path = tmp_path / "contracts" / "bad.contract.yml"
        path.parent.mkdir(parents=True)
        path.write_text("description: no module key here\n")
        with pytest.raises(ProjectPlanError, match="missing required top-level 'module' key"):
            ProjectPlan.from_spec_dir(tmp_path)

    def test_non_list_depends_on_raises(self, tmp_path):
        path = tmp_path / "contracts" / "bad.contract.yml"
        path.parent.mkdir(parents=True)
        path.write_text("module: bad\ndepends_on: not_a_list\n")
        with pytest.raises(ProjectPlanError, match="'depends_on' must be a list"):
            ProjectPlan.from_spec_dir(tmp_path)

    def test_invalid_yaml_raises(self, tmp_path):
        path = tmp_path / "contracts" / "bad.contract.yml"
        path.parent.mkdir(parents=True)
        path.write_text("module: [unclosed\n")
        with pytest.raises(ProjectPlanError, match="invalid YAML"):
            ProjectPlan.from_spec_dir(tmp_path)

    def test_cycle_across_yaml_files_is_still_rejected(self, tmp_path):
        _write_contract(tmp_path / "contracts" / "a.contract.yml", "a", depends_on=["b"])
        _write_contract(tmp_path / "contracts" / "b.contract.yml", "b", depends_on=["a"])
        with pytest.raises(ProjectPlanError, match="cycle"):
            ProjectPlan.from_spec_dir(tmp_path)


# --- ProjectArchitect.plan ------------------------------------------------

class TestArchitectPlan:
    def test_happy_path(self):
        result = _plan_with([
            {"name": "db", "description": "sqlite store", "depends_on": []},
            {"name": "api", "description": "flask routes", "depends_on": ["db"]},
        ])
        assert result.success
        assert result.plan.build_order == ["db", "api"]

    def test_malformed_module_entry_is_a_failed_result_not_a_raise(self):
        result = _plan_with([{"description": "no name here"}])
        assert result.success is False
        assert result.plan is None
        assert "malformed" in result.error

    def test_cycle_from_llm_is_a_failed_result(self):
        result = _plan_with([
            {"name": "a", "description": "d", "depends_on": ["b"]},
            {"name": "b", "description": "d", "depends_on": ["a"]},
        ])
        assert result.success is False
        assert "cycle" in result.error

    def test_emits_contract_decomposed_audit_event(self, tmp_path):
        from src.audit.local_client import LocalAuditClient
        from src.audit.schemas import AuditEventType
        from src.audit.store import AuditQuery

        audit = LocalAuditClient(database_url=f"sqlite:///{tmp_path / 'a.db'}")
        with patch.object(
            ProjectArchitect, "_generate_plan",
            return_value=[{"name": "db", "description": "store", "depends_on": []}],
        ):
            ProjectArchitect(llm_client=object(), audit_client=audit, model_id="m").plan("spec")
        events = audit._store.query(
            AuditQuery(event_types=[AuditEventType.CONTRACT_DECOMPOSED], limit=10)
        ).events
        assert len(events) == 1
        assert events[0].payload["decomposition_type"] == "project"
        assert events[0].payload["build_order"] == ["db"]


# --- _extract_modules parsing -------------------------------------------

class TestExtractModules:
    def test_parses_fenced_json_object(self):
        content = 'here you go:\n```json\n{"modules": [{"name": "a", "description": "d"}]}\n```'
        assert ProjectArchitect._extract_modules(content) == [{"name": "a", "description": "d"}]

    def test_parses_bare_json_object(self):
        assert ProjectArchitect._extract_modules('{"modules": [{"name": "a"}]}') == [{"name": "a"}]

    def test_parses_bare_json_array(self):
        assert ProjectArchitect._extract_modules('[{"name": "a"}]') == [{"name": "a"}]

    def test_no_json_raises(self):
        with pytest.raises(ProjectPlanError, match="no JSON"):
            ProjectArchitect._extract_modules("sorry, I can't help with that")

    def test_empty_modules_list_raises(self):
        with pytest.raises(ProjectPlanError, match="non-empty"):
            ProjectArchitect._extract_modules('{"modules": []}')
