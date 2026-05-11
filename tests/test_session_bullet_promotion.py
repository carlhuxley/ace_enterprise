"""Tests for session bullet promotion on GREEN phase (ace_enterprise-f7n)."""
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.storage.schemas import CuratorOutput, DeltaBullet, ReflectorOutput


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestReflectorOutputSessionBullets:
    def test_session_bullets_field_defaults_empty(self):
        output = ReflectorOutput(quality_score=0.8)
        assert output.session_bullets == []

    def test_session_bullets_accepts_delta_bullets(self):
        bullet = DeltaBullet(section="session-wins", content="Pattern works", tags=["tdd"])
        output = ReflectorOutput(quality_score=0.9, session_bullets=[bullet])
        assert len(output.session_bullets) == 1
        assert output.session_bullets[0].section == "session-wins"


class TestDeltaBulletContentHash:
    def test_content_hash_is_deterministic(self):
        b = DeltaBullet(section="session-wins", content="Test pattern")
        assert b.content_hash == b.content_hash

    def test_content_hash_same_for_equivalent_content(self):
        b1 = DeltaBullet(section="s", content="  Hello world  ")
        b2 = DeltaBullet(section="s", content="Hello world")
        assert b1.content_hash == b2.content_hash

    def test_content_hash_differs_for_different_content(self):
        b1 = DeltaBullet(section="s", content="Pattern A")
        b2 = DeltaBullet(section="s", content="Pattern B")
        assert b1.content_hash != b2.content_hash


# ---------------------------------------------------------------------------
# TDD agent session bullet promotion
# ---------------------------------------------------------------------------

def make_agent(tmp_path, playbook_manager=None):
    from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

    ensemble = MagicMock()
    ensemble.models = [("openai", "gpt-4o", None)]
    ensemble.playbook_manager = playbook_manager or MagicMock()
    ensemble.playbook_id = "test-playbook"

    return AutonomousTDDAgent(
        ensemble_learner=ensemble,
        test_reviewer=MagicMock(),
        project_root=tmp_path,
        test_dir=tmp_path / "tests",
        src_dir=tmp_path / "src",
    )


class TestBuildSessionBullet:
    def test_bullet_targets_session_wins_section(self, tmp_path):
        agent = make_agent(tmp_path)
        from src.agents.autonomous_tdd_agent import TestIncrement
        inc = TestIncrement(
            test_name="test_process_order",
            description="Process an order and return confirmation",
            test_file=tmp_path / "tests" / "test_order.py",
            implementation_file=tmp_path / "src" / "order.py",
        )
        bullet = agent._build_session_bullet(inc, cycle_number=2)
        assert bullet.section == "session-wins"

    def test_bullet_content_includes_test_name(self, tmp_path):
        agent = make_agent(tmp_path)
        from src.agents.autonomous_tdd_agent import TestIncrement
        inc = TestIncrement(
            test_name="test_process_order",
            description="Process an order",
            test_file=tmp_path / "tests" / "test_order.py",
            implementation_file=tmp_path / "src" / "order.py",
        )
        bullet = agent._build_session_bullet(inc, cycle_number=1)
        assert "test_process_order" in bullet.content

    def test_bullet_content_includes_cycle_number(self, tmp_path):
        agent = make_agent(tmp_path)
        from src.agents.autonomous_tdd_agent import TestIncrement
        inc = TestIncrement(
            test_name="test_foo",
            description="Foo works",
            test_file=tmp_path / "tests" / "test_foo.py",
            implementation_file=tmp_path / "src" / "foo.py",
        )
        bullet = agent._build_session_bullet(inc, cycle_number=3)
        assert "3" in bullet.content

    def test_bullet_tags_include_tdd_and_session_win(self, tmp_path):
        agent = make_agent(tmp_path)
        from src.agents.autonomous_tdd_agent import TestIncrement
        inc = TestIncrement(
            test_name="test_foo",
            description="Foo works",
            test_file=tmp_path / "tests" / "test_foo.py",
            implementation_file=tmp_path / "src" / "foo.py",
        )
        bullet = agent._build_session_bullet(inc, cycle_number=1)
        assert "tdd" in bullet.tags
        assert "session-win" in bullet.tags


class TestPromoteSessionBullet:
    def test_calls_curator_apply_updates(self, tmp_path):
        agent = make_agent(tmp_path)
        agent.curator = MagicMock()
        from src.agents.autonomous_tdd_agent import TestIncrement
        inc = TestIncrement(
            test_name="test_foo",
            description="Foo",
            test_file=tmp_path / "tests" / "test_foo.py",
            implementation_file=tmp_path / "src" / "foo.py",
        )
        agent._promote_session_bullet(inc, cycle_number=1)
        agent.curator.apply_updates.assert_called_once()

    def test_passes_session_wins_section(self, tmp_path):
        agent = make_agent(tmp_path)
        agent.curator = MagicMock()
        from src.agents.autonomous_tdd_agent import TestIncrement
        inc = TestIncrement(
            test_name="test_foo",
            description="Foo",
            test_file=tmp_path / "tests" / "test_foo.py",
            implementation_file=tmp_path / "src" / "foo.py",
        )
        agent._promote_session_bullet(inc, cycle_number=1)
        curator_output: CuratorOutput = agent.curator.apply_updates.call_args[0][1]
        assert len(curator_output.delta_bullets) == 1
        assert curator_output.delta_bullets[0].section == "session-wins"

    def test_no_op_when_playbook_manager_is_none(self, tmp_path):
        agent = make_agent(tmp_path)
        agent.playbook_manager = None
        agent.curator = MagicMock()
        from src.agents.autonomous_tdd_agent import TestIncrement
        inc = TestIncrement(
            test_name="test_foo",
            description="Foo",
            test_file=tmp_path / "tests" / "test_foo.py",
            implementation_file=tmp_path / "src" / "foo.py",
        )
        agent._promote_session_bullet(inc, cycle_number=1)
        agent.curator.apply_updates.assert_not_called()


# ---------------------------------------------------------------------------
# Playbook deduplication via content hash
# ---------------------------------------------------------------------------

class TestPlaybookManagerDeduplication:
    def test_duplicate_session_bullet_not_added_twice(self, tmp_path):
        from src.playbook.manager import PlaybookManager
        from src.storage.schemas import BulletCreate

        pm = PlaybookManager(storage_path=str(tmp_path / "playbook.json"))
        from src.storage.schemas import PlaybookCreate
        pid_obj = pm.create_playbook(PlaybookCreate(domain="test", base_model="gpt-4o"))
        pid = pid_obj.playbook_id

        bullet = DeltaBullet(
            section="session-wins",
            content="GREEN cycle 1: test_foo passed",
            tags=["tdd"],
        )

        pm.apply_delta(pid, [bullet])
        pm.apply_delta(pid, [bullet])  # second call — same content

        playbook = pm.get_playbook(pid)
        session_bullets = playbook.sections.get("session-wins", [])
        assert len(session_bullets) == 1

    def test_different_bullets_both_added(self, tmp_path):
        from src.playbook.manager import PlaybookManager

        pm = PlaybookManager(storage_path=str(tmp_path / "playbook.json"))
        from src.storage.schemas import PlaybookCreate
        pid_obj = pm.create_playbook(PlaybookCreate(domain="test", base_model="gpt-4o"))
        pid = pid_obj.playbook_id

        b1 = DeltaBullet(section="session-wins", content="GREEN cycle 1: test_foo", tags=[])
        b2 = DeltaBullet(section="session-wins", content="GREEN cycle 2: test_bar", tags=[])

        pm.apply_delta(pid, [b1, b2])

        playbook = pm.get_playbook(pid)
        assert len(playbook.sections.get("session-wins", [])) == 2
