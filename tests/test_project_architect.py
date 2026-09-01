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
