"""Tests for TypeScriptWorkerAgent (ace_enterprise#66: CGR3 retrieval wiring)."""
from unittest.mock import MagicMock

from src.agents.language_pod import PodSpec
from src.agents.typescript_worker_agent import TypeScriptWorkerAgent


def _llm(content="export function process(): void {}", tokens=80):
    client = MagicMock()
    client.generate.return_value = {
        "content": content,
        "tokens_used": tokens,
        "latency_ms": 20,
        "model": "gpt-4o",
    }
    return client


def _spec(tmp_path, cycle=1):
    return PodSpec(
        feature_requirement="Process an order",
        test_file=tmp_path / "order.test.ts",
        implementation_file=tmp_path / "order.ts",
        cycle_number=cycle,
    )


def _captured_prompt(worker):
    return worker.llm_client.generate.call_args[0][0]


class TestGetHardRules:
    def test_playbook_bullets_used_when_manager_set(self, tmp_path):
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("b1", "always validate inputs at boundaries")]
        w = TypeScriptWorkerAgent(_llm(), playbook_manager=pm)
        w.generate_implementation(_spec(tmp_path))
        assert "always validate inputs at boundaries" in _captured_prompt(w)

    def test_default_hard_rules_used_when_no_playbook(self, tmp_path):
        w = TypeScriptWorkerAgent(_llm())
        w.generate_implementation(_spec(tmp_path))
        assert "camelCase" in _captured_prompt(w)

    def test_records_last_retrieved_bullet_ids(self, tmp_path):
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("b1", "one"), ("b2", "two")]
        w = TypeScriptWorkerAgent(_llm(), playbook_manager=pm)
        w.generate_implementation(_spec(tmp_path))
        assert w.last_retrieved_bullet_ids == ["b1", "b2"]

    def test_last_retrieved_bullet_ids_empty_when_no_playbook(self, tmp_path):
        w = TypeScriptWorkerAgent(_llm())
        w.generate_implementation(_spec(tmp_path))
        assert w.last_retrieved_bullet_ids == []

    def test_retrieval_service_present_uses_its_apply_list_not_the_full_playbook(self, tmp_path):
        # ace_enterprise#66: a configured retrieval_service (CGR3) takes
        # priority over the unconditional get_bullets_with_ids() dump, even
        # when a playbook_manager is ALSO set.
        from src.retrieval.schemas import KnowledgeResponse, RankedBullet
        from src.storage.schemas import Bullet

        applied_bullet = Bullet(
            id="ctx-001", section="strategies_and_hard_rules", content="use readonly for immutable properties",
            created_at="2026-01-01T00:00:00", tags=[],
        )
        response = KnowledgeResponse(
            apply=[RankedBullet(bullet=applied_bullet, semantic_score=0.9, context_score=0.8, combined_score=0.85)],
        )
        service = MagicMock()
        service.get_guidance_for_implementation.return_value = response
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("ctx-999", "irrelevant bullet from the full dump")]

        w = TypeScriptWorkerAgent(_llm(), playbook_manager=pm, retrieval_service=service)
        w.generate_implementation(_spec(tmp_path))

        assert w.last_retrieved_bullet_ids == ["ctx-001"]
        assert "use readonly for immutable properties" in _captured_prompt(w)
        assert "irrelevant bullet from the full dump" not in _captured_prompt(w)
        pm.get_bullets_with_ids.assert_not_called()

    def test_retrieval_service_passes_the_feature_requirement_as_the_query(self, tmp_path):
        from src.retrieval.schemas import KnowledgeResponse

        service = MagicMock()
        service.get_guidance_for_implementation.return_value = KnowledgeResponse()
        w = TypeScriptWorkerAgent(_llm(), retrieval_service=service)
        w.generate_implementation(_spec(tmp_path))
        service.get_guidance_for_implementation.assert_called_once()
        args, kwargs = service.get_guidance_for_implementation.call_args
        assert args[0] == "Process an order"

    def test_retrieval_service_receives_a_populated_retrieval_context(self, tmp_path):
        # ace_enterprise#66 gap 2: context=None meant CGR3's team/tech_stack/
        # project scoring dimensions never had anything real to score against.
        from src.retrieval.schemas import KnowledgeResponse, RetrievalContext

        service = MagicMock()
        service.get_guidance_for_implementation.return_value = KnowledgeResponse()
        w = TypeScriptWorkerAgent(
            _llm(), retrieval_service=service,
            team_id="payments", project_id="checkout-svc", project_path="/repo/checkout-svc",
        )
        w.generate_implementation(_spec(tmp_path))
        _, kwargs = service.get_guidance_for_implementation.call_args
        context = kwargs["context"]
        assert isinstance(context, RetrievalContext)
        assert context.team_id == "payments"
        assert context.project_id == "checkout-svc"
        assert context.project_path == "/repo/checkout-svc"
        assert context.tech_stack == {"language": "typescript", "testing": "vitest"}

    def test_retrieval_service_empty_apply_falls_back_to_default_hard_rules(self, tmp_path):
        # _DEFAULT_HARD_RULES are universal TypeScript style/safety rules,
        # so an empty CGR3 result still falls back to them rather than
        # leaving GREEN with zero hard constraints.
        from src.retrieval.schemas import KnowledgeResponse

        service = MagicMock()
        service.get_guidance_for_implementation.return_value = KnowledgeResponse(apply=[])
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("ctx-999", "should not be used")]

        w = TypeScriptWorkerAgent(_llm(), playbook_manager=pm, retrieval_service=service)
        w.generate_implementation(_spec(tmp_path))

        assert w.last_retrieved_bullet_ids == []
        assert "should not be used" not in _captured_prompt(w)
        assert "camelCase" in _captured_prompt(w)
        pm.get_bullets_with_ids.assert_not_called()

    def test_retrieval_service_failure_falls_back_to_the_full_playbook_dump(self, tmp_path):
        service = MagicMock()
        service.get_guidance_for_implementation.side_effect = RuntimeError("embedding service down")
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("ctx-1", "fallback bullet")]

        w = TypeScriptWorkerAgent(_llm(), playbook_manager=pm, retrieval_service=service)
        w.generate_implementation(_spec(tmp_path))

        assert w.last_retrieved_bullet_ids == ["ctx-1"]
        assert "fallback bullet" in _captured_prompt(w)

    def test_no_retrieval_service_configured_uses_the_full_playbook_dump_unchanged(self, tmp_path):
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("ctx-1", "the old behavior")]
        w = TypeScriptWorkerAgent(_llm(), playbook_manager=pm)
        w.generate_implementation(_spec(tmp_path))
        assert "the old behavior" in _captured_prompt(w)
