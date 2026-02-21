"""Tests for 'ace learn' audit integration.

Verifies that manually adding knowledge emits proper audit events:
- Event: KNOWLEDGE_ADDED
- Fields: content, section, tags, created_by: 'human', source: 'cli'
"""
from unittest.mock import MagicMock


class TestLearnWithAudit:
    """Tests for learn_with_audit helper function."""

    def test_emits_knowledge_added_event(self):
        """Should emit KNOWLEDGE_ADDED when adding knowledge."""
        from src.playbook.learn_cli import learn_with_audit
        from src.audit.schemas import AuditEventType

        mock_audit = MagicMock()
        mock_manager = MagicMock()
        mock_bullet = MagicMock()
        mock_bullet.id = "ctx-001"
        mock_manager.add_bullet.return_value = mock_bullet

        learn_with_audit(
            manager=mock_manager,
            playbook_id="test-playbook",
            content="Always use pytest fixtures",
            section="strategies_and_hard_rules",
            tags=["testing", "python"],
            audit_client=mock_audit,
        )

        mock_audit.emit_simple.assert_called_once()
        call_args = mock_audit.emit_simple.call_args
        assert call_args.kwargs["event_type"] == AuditEventType.KNOWLEDGE_ADDED

    def test_payload_includes_full_content(self):
        """Should include full content for human visibility."""
        from src.playbook.learn_cli import learn_with_audit

        mock_audit = MagicMock()
        mock_manager = MagicMock()
        mock_bullet = MagicMock()
        mock_bullet.id = "ctx-001"
        mock_manager.add_bullet.return_value = mock_bullet

        content = "Always use pytest fixtures for test setup"

        learn_with_audit(
            manager=mock_manager,
            playbook_id="test-playbook",
            content=content,
            section="strategies_and_hard_rules",
            tags=["testing"],
            audit_client=mock_audit,
        )

        call_args = mock_audit.emit_simple.call_args
        payload = call_args.kwargs["payload"]

        # Should have full content for human visibility
        assert "content" in payload
        assert payload["content"] == content

    def test_payload_includes_section(self):
        """Should include section in payload."""
        from src.playbook.learn_cli import learn_with_audit

        mock_audit = MagicMock()
        mock_manager = MagicMock()
        mock_bullet = MagicMock()
        mock_bullet.id = "ctx-001"
        mock_manager.add_bullet.return_value = mock_bullet

        learn_with_audit(
            manager=mock_manager,
            playbook_id="test-playbook",
            content="Test content",
            section="code_snippets",
            tags=[],
            audit_client=mock_audit,
        )

        call_args = mock_audit.emit_simple.call_args
        payload = call_args.kwargs["payload"]
        assert payload["section"] == "code_snippets"

    def test_payload_includes_tags(self):
        """Should include tags in payload."""
        from src.playbook.learn_cli import learn_with_audit

        mock_audit = MagicMock()
        mock_manager = MagicMock()
        mock_bullet = MagicMock()
        mock_bullet.id = "ctx-001"
        mock_manager.add_bullet.return_value = mock_bullet

        learn_with_audit(
            manager=mock_manager,
            playbook_id="test-playbook",
            content="Test content",
            section="strategies_and_hard_rules",
            tags=["python", "best-practices"],
            audit_client=mock_audit,
        )

        call_args = mock_audit.emit_simple.call_args
        payload = call_args.kwargs["payload"]
        assert payload["tags"] == ["python", "best-practices"]

    def test_actor_type_is_human(self):
        """Should set actor_type to 'human' for manual additions."""
        from src.playbook.learn_cli import learn_with_audit

        mock_audit = MagicMock()
        mock_manager = MagicMock()
        mock_bullet = MagicMock()
        mock_bullet.id = "ctx-001"
        mock_manager.add_bullet.return_value = mock_bullet

        learn_with_audit(
            manager=mock_manager,
            playbook_id="test-playbook",
            content="Test content",
            section="strategies_and_hard_rules",
            tags=[],
            audit_client=mock_audit,
        )

        call_args = mock_audit.emit_simple.call_args
        assert call_args.kwargs["actor_type"] == "human"

    def test_payload_includes_source_cli(self):
        """Should include source: 'cli' in payload."""
        from src.playbook.learn_cli import learn_with_audit

        mock_audit = MagicMock()
        mock_manager = MagicMock()
        mock_bullet = MagicMock()
        mock_bullet.id = "ctx-001"
        mock_manager.add_bullet.return_value = mock_bullet

        learn_with_audit(
            manager=mock_manager,
            playbook_id="test-playbook",
            content="Test content",
            section="strategies_and_hard_rules",
            tags=[],
            audit_client=mock_audit,
        )

        call_args = mock_audit.emit_simple.call_args
        payload = call_args.kwargs["payload"]
        assert payload["source"] == "cli"

    def test_returns_created_bullet(self):
        """Should return the created bullet."""
        from src.playbook.learn_cli import learn_with_audit

        mock_audit = MagicMock()
        mock_manager = MagicMock()
        mock_bullet = MagicMock()
        mock_bullet.id = "ctx-001"
        mock_manager.add_bullet.return_value = mock_bullet

        result = learn_with_audit(
            manager=mock_manager,
            playbook_id="test-playbook",
            content="Test content",
            section="strategies_and_hard_rules",
            tags=[],
            audit_client=mock_audit,
        )

        assert result == mock_bullet

    def test_payload_includes_bullet_id(self):
        """Should include created bullet ID in payload."""
        from src.playbook.learn_cli import learn_with_audit

        mock_audit = MagicMock()
        mock_manager = MagicMock()
        mock_bullet = MagicMock()
        mock_bullet.id = "ctx-042"
        mock_manager.add_bullet.return_value = mock_bullet

        learn_with_audit(
            manager=mock_manager,
            playbook_id="test-playbook",
            content="Test content",
            section="strategies_and_hard_rules",
            tags=[],
            audit_client=mock_audit,
        )

        call_args = mock_audit.emit_simple.call_args
        payload = call_args.kwargs["payload"]
        assert payload["bullet_id"] == "ctx-042"
