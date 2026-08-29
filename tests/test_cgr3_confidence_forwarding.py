"""Regression: min_confidence must actually reach every filter layer.

InstitutionalKnowledgeService.get_guidance(min_confidence=...) used to only
affect its own pre-filter (_get_bullets()). ContextGraphRetriever.retrieve()
called base_retriever.retrieve() without forwarding min_confidence at all,
so BulletRetriever silently re-applied its own hardcoded 0.5 default --
meaning a freshly Curator-written bullet (confidence 0.3, see
src/playbook/manager.py's apply_delta) could never be retrieved via
get_guidance() no matter what min_confidence the caller passed.

No live LLM or podman needed -- pure playbook/retrieval plumbing.
"""
from pathlib import Path

import pytest

from src.playbook.manager import PlaybookManager
from src.playbook.retrieval import BulletRetriever
from src.retrieval.cgr3_retriever import ContextGraphRetriever
from src.retrieval.schemas import RetrievalContext
from src.retrieval.service import InstitutionalKnowledgeService
from src.storage.schemas import DeltaBullet

_SECTION = "strategies_and_hard_rules"
_CONTENT = "Always double-check arithmetic operators match intent."


@pytest.fixture
def playbook_manager(tmp_path):
    pm = PlaybookManager(storage_path=str(tmp_path / "playbooks"))
    pm.get_or_create_playbook("pb1")
    return pm


@pytest.fixture
def low_confidence_bullet(playbook_manager):
    """A bullet at confidence 0.3, exactly like a real Curator write."""
    added = playbook_manager.apply_delta(
        "pb1", [DeltaBullet(section=_SECTION, content=_CONTENT)],
    )
    assert added[0].confidence_score == 0.3  # sanity: matches apply_delta's real behavior
    return added[0]


class TestContextGraphRetrieverForwardsMinConfidence:
    def test_default_min_confidence_excludes_low_confidence_bullet(self, low_confidence_bullet):
        retriever = ContextGraphRetriever(base_retriever=BulletRetriever(similarity_threshold=0.0))
        response = retriever.retrieve(query="arithmetic operators", bullets=[low_confidence_bullet])
        assert response.apply == []
        assert response.ask_first == []

    def test_explicit_min_confidence_zero_includes_it(self, low_confidence_bullet):
        retriever = ContextGraphRetriever(base_retriever=BulletRetriever(similarity_threshold=0.0))
        response = retriever.retrieve(
            query="arithmetic operators", bullets=[low_confidence_bullet], min_confidence=0.0,
        )
        contents = [rb.bullet.content for rb in response.apply + response.ask_first]
        assert _CONTENT in contents


class TestGetGuidanceForwardsMinConfidence:
    def test_default_min_confidence_excludes_low_confidence_bullet(
        self, playbook_manager, low_confidence_bullet,
    ):
        service = InstitutionalKnowledgeService(
            playbook_manager=playbook_manager,
            default_playbook_id="pb1",
            retriever=ContextGraphRetriever(base_retriever=BulletRetriever(similarity_threshold=0.0)),
        )
        response = service.get_guidance(query="arithmetic operators", playbook_id="pb1")
        assert response.apply == []
        assert response.ask_first == []

    def test_min_confidence_zero_surfaces_a_fresh_curator_bullet(
        self, playbook_manager, low_confidence_bullet,
    ):
        service = InstitutionalKnowledgeService(
            playbook_manager=playbook_manager,
            default_playbook_id="pb1",
            retriever=ContextGraphRetriever(base_retriever=BulletRetriever(similarity_threshold=0.0)),
        )
        response = service.get_guidance(
            query="arithmetic operators",
            context=RetrievalContext(domain="tdd"),
            playbook_id="pb1",
            min_confidence=0.0,
        )
        contents = [rb.bullet.content for rb in response.apply + response.ask_first]
        assert _CONTENT in contents, (
            f"apply={[rb.bullet.content for rb in response.apply]} "
            f"ask_first={[rb.bullet.content for rb in response.ask_first]}"
        )
