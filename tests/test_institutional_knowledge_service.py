"""Tests for InstitutionalKnowledgeService (src/retrieval/service.py) -- the
top-level CGR3 entry point (the `get_guidance` MCP tool sits on top of this).
Previously had zero test coverage anywhere.

Uses a real, file-based PlaybookManager (tmp_path-scoped) for bullet storage
-- cross-playbook retrieval specifically depends on PlaybookManager's private
_playbooks dict (see _get_bullets()), which only a real instance has (a
Postgres-backed playbook manager wouldn't support it -- see
TestCrossPlaybookNeedsPrivateAttr below). A stub retriever isolates these
tests from the full CGR3 RANK/REASON pipeline, which is covered separately
in test_cgr3_retriever.py.
"""
import pytest

from src.playbook.manager import PlaybookManager
from src.retrieval.schemas import KnowledgeResponse, RankedBullet, RetrievalContext
from src.retrieval.service import InstitutionalKnowledgeService, get_knowledge_service
from src.storage.schemas import BulletCreate


class _StubRetriever:
    """Returns a KnowledgeResponse reporting exactly which bullets it was
    handed, tagged APPLY -- isolates service-level bullet-gathering logic
    from CGR3's own RANK/REASON scoring (tested separately)."""

    def __init__(self):
        self.last_call = None

    def retrieve(self, query, bullets, context=None, top_k=10, min_confidence=0.5):
        self.last_call = dict(
            query=query, bullets=bullets, context=context,
            top_k=top_k, min_confidence=min_confidence,
        )
        apply = [
            RankedBullet(bullet=b, semantic_score=1.0, context_score=1.0, combined_score=1.0)
            for b in bullets
        ]
        return KnowledgeResponse(apply=apply, total_candidates=len(bullets), query=query)


@pytest.fixture
def playbook_manager(tmp_path):
    return PlaybookManager(storage_path=str(tmp_path / "playbooks"))


def _add_bullet(pm, playbook_id, content, section="strategies_and_hard_rules", **kw):
    pm.get_or_create_playbook(playbook_id)
    return pm.add_bullet(playbook_id, BulletCreate(content=content, section=section, **kw))


# ---------------------------------------------------------------------------
# get_guidance: bullet-gathering (_get_bullets) behavior
# ---------------------------------------------------------------------------

class TestGetGuidance:
    def test_no_playbook_manager_returns_empty_response(self):
        service = InstitutionalKnowledgeService(playbook_manager=None, retriever=_StubRetriever())
        response = service.get_guidance(query="anything")
        assert response.apply == [] and response.total_candidates == 0

    def test_no_bullets_in_playbook_returns_empty_response(self, playbook_manager):
        playbook_manager.get_or_create_playbook("pb1")
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=_StubRetriever())
        response = service.get_guidance(query="anything", playbook_id="pb1")
        assert response.apply == []

    def test_primary_playbook_bullets_are_retrieved(self, playbook_manager):
        _add_bullet(playbook_manager, "pb1", "use pathlib", confidence_score=0.9)
        stub = _StubRetriever()
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=stub)
        response = service.get_guidance(query="q", playbook_id="pb1")
        assert len(response.apply) == 1
        assert response.apply[0].bullet.content == "use pathlib"

    def test_default_playbook_id_used_when_not_specified(self, playbook_manager):
        _add_bullet(playbook_manager, "default-pb", "use pathlib", confidence_score=0.9)
        stub = _StubRetriever()
        service = InstitutionalKnowledgeService(
            playbook_manager=playbook_manager, retriever=stub, default_playbook_id="default-pb",
        )
        response = service.get_guidance(query="q")
        assert len(response.apply) == 1

    def test_cross_playbook_included_by_default(self, playbook_manager):
        _add_bullet(playbook_manager, "pb1", "primary bullet", confidence_score=0.9)
        _add_bullet(playbook_manager, "pb2", "other team's bullet", confidence_score=0.9)
        stub = _StubRetriever()
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=stub)
        response = service.get_guidance(query="q", playbook_id="pb1")
        contents = {rb.bullet.content for rb in response.apply}
        assert contents == {"primary bullet", "other team's bullet"}

    def test_cross_playbook_excluded_when_disabled(self, playbook_manager):
        _add_bullet(playbook_manager, "pb1", "primary bullet", confidence_score=0.9)
        _add_bullet(playbook_manager, "pb2", "other team's bullet", confidence_score=0.9)
        stub = _StubRetriever()
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=stub)
        response = service.get_guidance(query="q", playbook_id="pb1", include_cross_playbook=False)
        contents = {rb.bullet.content for rb in response.apply}
        assert contents == {"primary bullet"}

    def test_min_confidence_filters_before_retrieval(self, playbook_manager):
        _add_bullet(playbook_manager, "pb1", "low conf", confidence_score=0.2)
        _add_bullet(playbook_manager, "pb1", "high conf", confidence_score=0.9)
        stub = _StubRetriever()
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=stub)
        response = service.get_guidance(query="q", playbook_id="pb1", min_confidence=0.5)
        assert [rb.bullet.content for rb in response.apply] == ["high conf"]

    def test_min_confidence_zero_surfaces_low_confidence_curator_bullets(self, playbook_manager):
        # Regression-adjacent to test_cgr3_confidence_forwarding.py: this
        # checks _get_bullets()'s own pre-filter, not the base_retriever's.
        _add_bullet(playbook_manager, "pb1", "curator bullet", confidence_score=0.3)
        stub = _StubRetriever()
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=stub)
        response = service.get_guidance(query="q", playbook_id="pb1", min_confidence=0.0)
        assert len(response.apply) == 1

    def test_domain_filter_matches_applicable_domains(self, playbook_manager):
        _add_bullet(playbook_manager, "pb1", "fintech rule", confidence_score=0.9, applicable_domains=["fintech"])
        _add_bullet(playbook_manager, "pb1", "healthcare rule", confidence_score=0.9, applicable_domains=["healthcare"])
        stub = _StubRetriever()
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=stub)
        response = service.get_guidance(query="q", playbook_id="pb1", domain="fintech")
        assert [rb.bullet.content for rb in response.apply] == ["fintech rule"]

    def test_domain_filter_also_matches_tags(self, playbook_manager):
        # _get_bullets()'s domain filter checks tags too, unlike
        # BulletRetriever's own domain filter (applicable_domains only).
        _add_bullet(playbook_manager, "pb1", "tagged rule", confidence_score=0.9, tags=["fintech"])
        stub = _StubRetriever()
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=stub)
        response = service.get_guidance(query="q", playbook_id="pb1", domain="fintech")
        assert len(response.apply) == 1

    def test_domainless_bullet_passes_any_domain_filter(self, playbook_manager):
        _add_bullet(playbook_manager, "pb1", "generic rule", confidence_score=0.9)
        stub = _StubRetriever()
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=stub)
        response = service.get_guidance(query="q", playbook_id="pb1", domain="fintech")
        assert len(response.apply) == 1

    def test_project_filter_matches_project_ids(self, playbook_manager):
        _add_bullet(playbook_manager, "pb1", "proj-a rule", confidence_score=0.9, project_ids=["proj-a"])
        _add_bullet(playbook_manager, "pb1", "proj-b rule", confidence_score=0.9, project_ids=["proj-b"])
        stub = _StubRetriever()
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=stub)
        response = service.get_guidance(query="q", playbook_id="pb1", project_id="proj-a")
        assert [rb.bullet.content for rb in response.apply] == ["proj-a rule"]

    def test_context_and_top_k_forwarded_to_retriever(self, playbook_manager):
        _add_bullet(playbook_manager, "pb1", "bullet", confidence_score=0.9)
        stub = _StubRetriever()
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=stub)
        ctx = RetrievalContext(domain="tdd")
        service.get_guidance(query="q", playbook_id="pb1", context=ctx, top_k=3)
        assert stub.last_call["context"] is ctx
        assert stub.last_call["top_k"] == 3


class TestCrossPlaybookNeedsPrivateAttr:
    def test_cross_playbook_silently_finds_nothing_without_playbooks_attr(self, playbook_manager):
        """_get_bullets() gates cross-playbook inclusion on
        hasattr(playbook_manager, '_playbooks') -- a playbook_manager without
        that private attribute (e.g. a Postgres-backed one) silently gets
        primary-playbook-only results even with include_cross_playbook=True,
        no error or warning. Documents the coupling rather than asserting
        it's fine."""
        _add_bullet(playbook_manager, "pb1", "primary", confidence_score=0.9)
        _add_bullet(playbook_manager, "pb2", "other", confidence_score=0.9)

        class _NoPrivateAttrManager:
            def get_playbook(self, playbook_id):
                return playbook_manager.get_playbook(playbook_id)

        stub = _StubRetriever()
        service = InstitutionalKnowledgeService(playbook_manager=_NoPrivateAttrManager(), retriever=stub)
        response = service.get_guidance(query="q", playbook_id="pb1", include_cross_playbook=True)
        assert [rb.bullet.content for rb in response.apply] == ["primary"]


# ---------------------------------------------------------------------------
# Convenience wrappers around get_guidance
# ---------------------------------------------------------------------------

def _capturing_get_guidance(service, captured):
    """A get_guidance replacement that records its args by name regardless
    of whether the caller (a get_guidance_* wrapper) passes them positionally
    or by keyword -- get_guidance_for_tdd uses positional query/context,
    the others use keywords."""
    import inspect
    sig = inspect.signature(InstitutionalKnowledgeService.get_guidance)

    def fake(*args, **kwargs):
        bound = sig.bind(service, *args, **kwargs)
        captured.update(bound.arguments)
        return KnowledgeResponse()

    return fake


class TestConvenienceWrappers:
    def test_get_guidance_for_tdd_builds_query_and_sets_tdd_domain(self, playbook_manager, monkeypatch):
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=_StubRetriever())
        captured = {}
        monkeypatch.setattr(service, "get_guidance", _capturing_get_guidance(service, captured))

        service.get_guidance_for_tdd(test_name="test_add", implementation_context="adds two numbers")

        assert "test_add" in captured["query"]
        assert "adds two numbers" in captured["query"]
        assert captured["domain"] == "tdd"
        assert captured["context"].domain == "tdd"

    def test_get_guidance_for_tdd_preserves_explicit_context_domain(self, playbook_manager, monkeypatch):
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=_StubRetriever())
        captured = {}
        monkeypatch.setattr(service, "get_guidance", _capturing_get_guidance(service, captured))

        ctx = RetrievalContext(domain="custom-domain")
        service.get_guidance_for_tdd(test_name="t", implementation_context="c", context=ctx)

        assert captured["context"].domain == "custom-domain"

    def test_get_guidance_for_implementation_builds_query(self, playbook_manager, monkeypatch):
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=_StubRetriever())
        captured = {}
        monkeypatch.setattr(service, "get_guidance", lambda **kw: captured.update(kw) or KnowledgeResponse())

        service.get_guidance_for_implementation("a login form")

        assert captured["query"] == "implementing: a login form"

    def test_get_anti_patterns_builds_query_and_domain(self, playbook_manager, monkeypatch):
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=_StubRetriever())
        captured = {}
        monkeypatch.setattr(service, "get_guidance", lambda **kw: captured.update(kw) or KnowledgeResponse())

        service.get_anti_patterns("database access")

        assert "database access" in captured["query"]
        assert captured["domain"] == "anti-patterns"


# ---------------------------------------------------------------------------
# format_guidance
# ---------------------------------------------------------------------------

class TestFormatGuidance:
    def test_no_results_returns_placeholder(self, playbook_manager):
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=_StubRetriever())
        text = service.format_guidance(KnowledgeResponse())
        assert text == "No relevant patterns found."

    def test_apply_bullets_are_listed(self, playbook_manager):
        bullet = _add_bullet(playbook_manager, "pb1", "use pathlib", confidence_score=0.9)
        response = KnowledgeResponse(apply=[
            RankedBullet(bullet=bullet, semantic_score=0.9, context_score=0.9, combined_score=0.9)
        ])
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=_StubRetriever())
        text = service.format_guidance(response)
        assert "use pathlib" in text
        assert "Confirmed patterns" in text

    def test_ask_first_excluded_by_default(self, playbook_manager):
        bullet = _add_bullet(playbook_manager, "pb1", "maybe use this", confidence_score=0.9)
        from src.retrieval.schemas import ContextGap
        response = KnowledgeResponse(ask_first=[
            RankedBullet(
                bullet=bullet, semantic_score=0.5, context_score=0.2, combined_score=0.3,
                context_gaps=[ContextGap(dimension="team", description="wrong team", severity=0.5)],
            )
        ])
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=_StubRetriever())
        text = service.format_guidance(response, include_ask_first=False)
        assert "maybe use this" not in text
        # has_results is True (ask_first is non-empty) so the early-return
        # placeholder branch is skipped, but include_ask_first=False means
        # neither formatting branch adds anything either -- format_guidance
        # falls back to the same placeholder text for this case too.
        assert text == "No relevant patterns found."

    def test_ask_first_included_with_gap_notes(self, playbook_manager):
        bullet = _add_bullet(playbook_manager, "pb1", "maybe use this", confidence_score=0.9)
        from src.retrieval.schemas import ContextGap
        response = KnowledgeResponse(ask_first=[
            RankedBullet(
                bullet=bullet, semantic_score=0.5, context_score=0.2, combined_score=0.3,
                context_gaps=[ContextGap(dimension="team", description="wrong team", severity=0.5)],
            )
        ])
        service = InstitutionalKnowledgeService(playbook_manager=playbook_manager, retriever=_StubRetriever())
        text = service.format_guidance(response, include_ask_first=True)
        assert "maybe use this" in text
        assert "wrong team" in text


# ---------------------------------------------------------------------------
# get_knowledge_service singleton
# ---------------------------------------------------------------------------

class TestKnowledgeServiceSingleton:
    def test_returns_same_instance_across_calls(self):
        import src.retrieval.service as service_module
        service_module._service_instance = None
        try:
            a = get_knowledge_service()
            b = get_knowledge_service()
            assert a is b
        finally:
            service_module._service_instance = None

    def test_force_new_creates_a_fresh_instance(self):
        import src.retrieval.service as service_module
        service_module._service_instance = None
        try:
            a = get_knowledge_service()
            b = get_knowledge_service(force_new=True)
            assert a is not b
        finally:
            service_module._service_instance = None
