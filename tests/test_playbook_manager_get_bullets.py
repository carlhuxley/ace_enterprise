"""Tests for PlaybookManager.get_bullets(section) (ace_enterprise-7eo)."""
import pytest

from src.playbook.manager import PlaybookManager
from src.storage.schemas import BulletCreate


def _manager(tmp_path):
    return PlaybookManager(storage_path=str(tmp_path / "playbook.json"))


def _add(pm, playbook_id, section, content):
    pm.add_bullet(playbook_id, BulletCreate(section=section, content=content))


# ---------------------------------------------------------------------------
# get_bullets — basic contract
# ---------------------------------------------------------------------------

class TestGetBullets:
    def test_returns_list(self, tmp_path):
        pm = _manager(tmp_path)
        pm.get_or_create_playbook("pb1")
        assert isinstance(pm.get_bullets("global-go-bullets"), list)

    def test_empty_when_no_playbooks_loaded(self, tmp_path):
        pm = _manager(tmp_path)
        assert pm.get_bullets("global-go-bullets") == []

    def test_empty_when_section_has_no_bullets(self, tmp_path):
        pm = _manager(tmp_path)
        pm.get_or_create_playbook("pb1")
        assert pm.get_bullets("global-go-bullets") == []

    def test_empty_when_section_absent_from_playbook(self, tmp_path):
        pm = _manager(tmp_path)
        pm.get_or_create_playbook("pb1")
        assert pm.get_bullets("strategies_and_hard_rules") == []

    def test_returns_content_strings_not_bullet_objects(self, tmp_path):
        pm = _manager(tmp_path)
        pm.get_or_create_playbook("pb1")
        _add(pm, "pb1", "global-go-bullets", "use errors.New for sentinel errors")
        result = pm.get_bullets("global-go-bullets")
        assert all(isinstance(s, str) for s in result)

    def test_returns_bullet_content_for_populated_section(self, tmp_path):
        pm = _manager(tmp_path)
        pm.get_or_create_playbook("pb1")
        _add(pm, "pb1", "global-go-bullets", "use errors.New for sentinel errors")
        result = pm.get_bullets("global-go-bullets")
        assert "use errors.New for sentinel errors" in result

    def test_returns_all_bullets_in_section(self, tmp_path):
        pm = _manager(tmp_path)
        pm.get_or_create_playbook("pb1")
        _add(pm, "pb1", "global-go-bullets", "prefer interfaces over concrete types")
        _add(pm, "pb1", "global-go-bullets", "use goroutines for concurrency")
        result = pm.get_bullets("global-go-bullets")
        assert len(result) == 2

    def test_does_not_return_bullets_from_other_sections(self, tmp_path):
        pm = _manager(tmp_path)
        pm.get_or_create_playbook("pb1")
        _add(pm, "pb1", "global-go-bullets", "go idiom")
        _add(pm, "pb1", "session-wins", "session win")
        result = pm.get_bullets("global-go-bullets")
        assert result == ["go idiom"]


# ---------------------------------------------------------------------------
# Multiple playbooks
# ---------------------------------------------------------------------------

class TestGetBulletsAcrossPlaybooks:
    def test_aggregates_across_multiple_playbooks(self, tmp_path):
        pm = _manager(tmp_path)
        pm.get_or_create_playbook("pb1")
        pm.get_or_create_playbook("pb2")
        _add(pm, "pb1", "global-go-bullets", "bullet from pb1")
        _add(pm, "pb2", "global-go-bullets", "bullet from pb2")
        result = pm.get_bullets("global-go-bullets")
        assert "bullet from pb1" in result
        assert "bullet from pb2" in result
        assert len(result) == 2

    def test_skips_playbooks_missing_the_section(self, tmp_path):
        pm = _manager(tmp_path)
        # Create a playbook without global-go-bullets by using raw create
        from src.storage.schemas import PlaybookCreate
        pb2 = pm.create_playbook(PlaybookCreate(domain="test", base_model="gpt-4o"))
        pm.get_or_create_playbook("pb1")
        _add(pm, "pb1", "global-go-bullets", "only bullet")
        result = pm.get_bullets("global-go-bullets")
        assert result == ["only bullet"]


# ---------------------------------------------------------------------------
# GoLanguagePod integration with real PlaybookManager
# ---------------------------------------------------------------------------

class TestGoLanguagePodWithRealPlaybook:
    def test_pod_uses_playbook_bullets_not_defaults(self, tmp_path):
        from unittest.mock import MagicMock, patch
        from src.agents.go_language_pod import GoLanguagePod

        pm = _manager(tmp_path)
        pm.get_or_create_playbook("go-playbook")
        _add(pm, "go-playbook", "global-go-bullets", "always return error as last value")

        captured = []
        client = MagicMock()
        client.generate.side_effect = lambda prompt, **kw: captured.append(prompt) or {
            "content": "package main", "tokens_used": 10, "latency_ms": 5, "model": "gpt-4o"
        }

        pod = GoLanguagePod(llm_client=client, playbook_manager=pm)
        spec_mock = MagicMock()
        spec_mock.feature_requirement = "Order processing"
        spec_mock.test_file.name = "order_test.go"
        spec_mock.implementation_file.name = "order.go"
        spec_mock.implementation_file.parent = tmp_path
        spec_mock.cycle_number = 1

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            pod.run_green(spec_mock)

        assert any("always return error as last value" in p for p in captured)
