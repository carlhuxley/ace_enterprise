"""Regression tests for the Curator/PlaybookManager "supersedes" mechanism.

Found via two real, reproducible failures in one session (building a
6-module project through `ace tdd`): a Reflector/Curator pass correctly
diagnosed an import-path bug and wrote a correct bullet, then a LATER pass
-- for the same recurring bug, hit again a few cycles on -- misdiagnosed it
and wrote a bullet giving the opposite instruction, with nothing to flag
that the two bullets now contradicted each other. Root cause:
Curator._build_synthesis_prompt showed the LLM only aggregate per-section
bullet counts, never the bullets' actual text, so it had no way to know it
was about to contradict something already there.
"""
from unittest.mock import MagicMock, patch

from src.core.curator.module import Curator
from src.playbook.manager import PlaybookManager
from src.storage.schemas import BulletCreate, DeltaBullet, Playbook, PlaybookCreate


def _curator():
    return Curator(playbook_manager=MagicMock(), llm_client=MagicMock())


def _manager(tmp_path):
    return PlaybookManager(storage_path=str(tmp_path / "playbooks"))


def _add(pm, playbook_id, section, content):
    return pm.add_bullet(playbook_id, BulletCreate(section=section, content=content))


# ---------------------------------------------------------------------------
# Curator._parse_synthesis: parsing the "[supersedes: ...]" marker
# ---------------------------------------------------------------------------

class TestParseSupersedesMarker:
    def test_single_id_is_parsed_and_stripped_from_content(self):
        response = """### Delta Bullets

#### Section: strategies_and_hard_rules
- Use flat imports: `from meta_optimizer import X`, never `from src.meta_optimizer import X`.
[supersedes: ctx-00123]
"""
        bullets, _ = _curator()._parse_synthesis(response)
        assert len(bullets) == 1
        assert bullets[0].supersedes == ["ctx-00123"]
        assert "supersedes" not in bullets[0].content.lower()
        assert "Use flat imports" in bullets[0].content

    def test_multiple_ids_are_parsed(self):
        response = """### Delta Bullets

#### Section: troubleshooting
- Corrected guidance replacing two earlier bullets.
[supersedes: ctx-001, ctx-002]
"""
        bullets, _ = _curator()._parse_synthesis(response)
        assert bullets[0].supersedes == ["ctx-001", "ctx-002"]

    def test_no_marker_means_empty_supersedes(self):
        response = """### Delta Bullets

#### Section: strategies_and_hard_rules
- A bullet that corrects nothing.
"""
        bullets, _ = _curator()._parse_synthesis(response)
        assert bullets[0].supersedes == []

    def test_marker_does_not_leak_into_a_later_bullet(self):
        response = """### Delta Bullets

#### Section: strategies_and_hard_rules
- First bullet, corrects something old.
[supersedes: ctx-999]
- Second, unrelated bullet.
"""
        bullets, _ = _curator()._parse_synthesis(response)
        assert len(bullets) == 2
        assert bullets[0].supersedes == ["ctx-999"]
        assert bullets[1].supersedes == []
        assert "supersedes" not in bullets[1].content.lower()

    def test_marker_is_case_insensitive(self):
        response = """### Delta Bullets

#### Section: strategies_and_hard_rules
- A bullet.
[Supersedes: ctx-01]
"""
        bullets, _ = _curator()._parse_synthesis(response)
        assert bullets[0].supersedes == ["ctx-01"]


# ---------------------------------------------------------------------------
# Curator._existing_bullets_block / _build_synthesis_prompt
# ---------------------------------------------------------------------------

class TestExistingBulletsInPrompt:
    def _playbook_with_one_bullet(self, tmp_path, content: str) -> tuple[Playbook, str]:
        pm = PlaybookManager(storage_path=str(tmp_path / "playbooks"))
        pb = pm.create_playbook(PlaybookCreate(domain="test", base_model="gpt-4o"))
        bullet = pm.add_bullet(pb.playbook_id, BulletCreate(
            section="strategies_and_hard_rules", content=content,
        ))
        return pm.get_playbook(pb.playbook_id), bullet.id

    def test_existing_bullet_id_and_content_appear_in_the_prompt(self, tmp_path):
        curator = _curator()
        playbook, bullet_id = self._playbook_with_one_bullet(tmp_path, "Use flat imports everywhere.")
        block = curator._existing_bullets_block(playbook)
        assert bullet_id in block
        assert "Use flat imports everywhere." in block

    def test_empty_playbook_produces_no_block(self, tmp_path):
        curator = _curator()
        pm = PlaybookManager(storage_path=str(tmp_path / "playbooks"))
        pb = pm.create_playbook(PlaybookCreate(domain="test", base_model="gpt-4o"))
        empty_playbook = pm.get_playbook(pb.playbook_id)
        assert curator._existing_bullets_block(empty_playbook) == ""

    def test_synthesis_prompt_instructs_checking_for_contradictions(self, tmp_path):
        curator = _curator()
        playbook, bullet_id = self._playbook_with_one_bullet(tmp_path, "Use flat imports everywhere.")
        from src.storage.schemas import ReflectorOutput
        prompt = curator._build_synthesis_prompt(
            reflector_output=ReflectorOutput(key_insight="something"),
            playbook=playbook,
            playbook_stats={"sections": {}},
            task_context=None,
        )
        assert "Existing Bullets" in prompt
        assert bullet_id in prompt
        assert "supersedes" in prompt.lower()
        assert "CONTRADICTS" in prompt


# ---------------------------------------------------------------------------
# PlaybookManager.apply_delta: acting on `supersedes`
# ---------------------------------------------------------------------------

class TestApplyDeltaSupersedes:
    def test_superseded_bullet_is_removed_when_replacement_is_added(self, tmp_path):
        pm = _manager(tmp_path)
        pm.get_or_create_playbook("pb1")
        old = _add(pm, "pb1", "strategies_and_hard_rules", "Use `src.`-qualified imports.")

        result = pm.apply_delta("pb1", [DeltaBullet(
            content="Use flat imports; there is no `src` package in this sandbox.",
            section="strategies_and_hard_rules",
            supersedes=[old.id],
        )])

        assert len(result) == 1
        remaining = pm.get_section_bullets("pb1", "strategies_and_hard_rules")
        assert old.id not in [b.id for b in remaining]
        assert any("flat imports" in b.content for b in remaining)

    def test_no_supersedes_leaves_existing_bullets_untouched(self, tmp_path):
        pm = _manager(tmp_path)
        pm.get_or_create_playbook("pb1")
        old = _add(pm, "pb1", "strategies_and_hard_rules", "An unrelated bullet.")

        pm.apply_delta("pb1", [DeltaBullet(
            content="A brand new, unrelated bullet.",
            section="strategies_and_hard_rules",
        )])

        remaining_ids = [b.id for b in pm.get_section_bullets("pb1", "strategies_and_hard_rules")]
        assert old.id in remaining_ids

    def test_rejected_replacement_does_not_remove_the_old_bullet(self, tmp_path):
        # If the new (superseding) bullet fails content safety and is never
        # added, removing the old one first would leave neither guidance in
        # the playbook -- worse than the contradiction itself.
        from src.playbook.content_safety import ContentRejectedError

        pm = _manager(tmp_path)
        pm.get_or_create_playbook("pb1")
        old = _add(pm, "pb1", "strategies_and_hard_rules", "Old guidance to keep.")

        with patch.object(pm, "add_bullet", side_effect=ContentRejectedError("blocked")):
            result = pm.apply_delta("pb1", [DeltaBullet(
                content="Replacement that gets rejected.",
                section="strategies_and_hard_rules",
                supersedes=[old.id],
            )])

        assert result == []
        remaining_ids = [b.id for b in pm.get_section_bullets("pb1", "strategies_and_hard_rules")]
        assert old.id in remaining_ids

    def test_supersedes_target_that_no_longer_exists_is_a_no_op(self, tmp_path):
        pm = _manager(tmp_path)
        pm.get_or_create_playbook("pb1")

        # Must not raise even though "ctx-ghost" was never a real bullet.
        result = pm.apply_delta("pb1", [DeltaBullet(
            content="A bullet that claims to supersede something nonexistent.",
            section="strategies_and_hard_rules",
            supersedes=["ctx-ghost"],
        )])

        assert len(result) == 1

    def test_multiple_superseded_ids_are_all_removed(self, tmp_path):
        pm = _manager(tmp_path)
        pm.get_or_create_playbook("pb1")
        old1 = _add(pm, "pb1", "strategies_and_hard_rules", "First old bullet.")
        old2 = _add(pm, "pb1", "strategies_and_hard_rules", "Second old bullet.")

        pm.apply_delta("pb1", [DeltaBullet(
            content="One bullet replacing both older ones.",
            section="strategies_and_hard_rules",
            supersedes=[old1.id, old2.id],
        )])

        remaining_ids = [b.id for b in pm.get_section_bullets("pb1", "strategies_and_hard_rules")]
        assert old1.id not in remaining_ids
        assert old2.id not in remaining_ids
