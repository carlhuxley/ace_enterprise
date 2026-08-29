"""Tests for Curator._parse_synthesis threading task_context onto DeltaBullet
(ace_enterprise: DeltaBullet/team_id gap). No LLM call needed --
_parse_synthesis is pure text parsing.

Note: Curator had zero test coverage anywhere before this file; scoped here
to the specific fix (team_id/project_ids/applicable_domains/tech_context
now surviving DeltaBullet -> apply_delta -> persisted Bullet), not a full
backfill of Curator's own synthesis/prompt-building logic.
"""
from unittest.mock import MagicMock

from src.core.curator.module import Curator

_SYNTHESIS_RESPONSE = """### Reasoning
Some reasoning here.

### Delta Bullets

#### Section: strategies_and_hard_rules
- always double-check arithmetic operators
"""


def _curator():
    return Curator(playbook_manager=MagicMock(), llm_client=MagicMock())


class TestParseSynthesisContextThreading:
    def test_no_task_context_leaves_fields_none(self):
        bullets, _ = _curator()._parse_synthesis(_SYNTHESIS_RESPONSE)
        assert bullets[0].team_id is None
        assert bullets[0].project_ids is None
        assert bullets[0].tags == []

    def test_tags_stamped_from_task_context(self):
        bullets, _ = _curator()._parse_synthesis(
            _SYNTHESIS_RESPONSE, task_context={"tags": ["currency_string_parsing"]},
        )
        assert bullets[0].tags == ["currency_string_parsing"]

    def test_team_id_stamped_from_task_context(self):
        bullets, _ = _curator()._parse_synthesis(
            _SYNTHESIS_RESPONSE, task_context={"team_id": "payments"},
        )
        assert bullets[0].team_id == "payments"

    def test_all_context_fields_stamped_from_task_context(self):
        bullets, _ = _curator()._parse_synthesis(
            _SYNTHESIS_RESPONSE,
            task_context={
                "team_id": "payments",
                "project_ids": ["proj-a"],
                "applicable_domains": ["fintech"],
                "tech_context": {"python": ">=3.10"},
                "tags": ["zero_division_sign"],
                "requirement": "unrelated task_context key, e.g. from TDDCycleRunner",
            },
        )
        bullet = bullets[0]
        assert bullet.team_id == "payments"
        assert bullet.project_ids == ["proj-a"]
        assert bullet.applicable_domains == ["fintech"]
        assert bullet.tech_context == {"python": ">=3.10"}
        assert bullet.tags == ["zero_division_sign"]

    def test_context_applies_to_every_bullet_synthesized(self):
        response = _SYNTHESIS_RESPONSE + "- a second bullet\n"
        bullets, _ = _curator()._parse_synthesis(
            response, task_context={"team_id": "payments"},
        )
        assert len(bullets) == 2
        assert all(b.team_id == "payments" for b in bullets)
