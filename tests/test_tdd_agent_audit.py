"""Tests for TDD agent audit integration.

Verifies that the TDD agent emits proper audit events:
- test_generated: When a test is written
- implementation_generated: When code is written
- pattern_learned: When a bullet is added
- cycle_completed: When RED→GREEN→REFACTOR→LEARN completes
"""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestTDDAgentAuditClient:
    """Tests for audit client integration in TDD agent."""

    def test_agent_has_audit_client(self):
        """TDD agent should have an audit client."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        mock_ensemble = MagicMock()
        mock_ensemble.models = [("openai", "gpt-4", None)]
        mock_ensemble.playbook_manager = MagicMock()
        mock_ensemble.playbook_id = "test-playbook"
        mock_reviewer = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            test_dir = project_root / "tests"
            src_dir = project_root / "src"
            test_dir.mkdir()
            src_dir.mkdir()

            with patch("src.agents.autonomous_tdd_agent.LLMClient"):
                with patch("src.playbook.retrieval.BulletRetriever"):
                    with patch("src.agents.autonomous_tdd_agent.LocalAuditClient") as mock_audit:
                        agent = AutonomousTDDAgent(
                            ensemble_learner=mock_ensemble,
                            test_reviewer=mock_reviewer,
                            project_root=project_root,
                            test_dir=test_dir,
                            src_dir=src_dir,
                        )

            assert hasattr(agent, "audit_client")

    def test_agent_creates_audit_client(self):
        """Should create audit client during initialization."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        mock_ensemble = MagicMock()
        mock_ensemble.models = [("openai", "gpt-4", None)]
        mock_ensemble.playbook_manager = MagicMock()
        mock_ensemble.playbook_id = "test-playbook"
        mock_reviewer = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            test_dir = project_root / "tests"
            src_dir = project_root / "src"
            test_dir.mkdir()
            src_dir.mkdir()

            with patch("src.agents.autonomous_tdd_agent.LLMClient"):
                with patch("src.playbook.retrieval.BulletRetriever"):
                    with patch("src.agents.autonomous_tdd_agent.LocalAuditClient") as MockAuditClient:
                        agent = AutonomousTDDAgent(
                            ensemble_learner=mock_ensemble,
                            test_reviewer=mock_reviewer,
                            project_root=project_root,
                            test_dir=test_dir,
                            src_dir=src_dir,
                        )

            # Verify LocalAuditClient was instantiated
            MockAuditClient.assert_called_once()


class TestTDDAgentEmitAuditEvent:
    """Tests for _emit_audit_event method."""

    def _create_agent_with_mock_audit(self):
        """Helper to create agent with mocked audit client."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        mock_ensemble = MagicMock()
        mock_ensemble.models = [("openai", "gpt-4", None)]
        mock_ensemble.playbook_manager = MagicMock()
        mock_ensemble.playbook_id = "test-playbook"
        mock_reviewer = MagicMock()
        mock_audit = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            test_dir = project_root / "tests"
            src_dir = project_root / "src"
            test_dir.mkdir()
            src_dir.mkdir()

            with patch("src.agents.autonomous_tdd_agent.LLMClient"):
                with patch("src.playbook.retrieval.BulletRetriever"):
                    with patch("src.agents.autonomous_tdd_agent.LocalAuditClient"):
                        agent = AutonomousTDDAgent(
                            ensemble_learner=mock_ensemble,
                            test_reviewer=mock_reviewer,
                            project_root=project_root,
                            test_dir=test_dir,
                            src_dir=src_dir,
                        )
                        agent.audit_client = mock_audit

            return agent, mock_audit

    def test_emits_test_generated_event(self):
        """Should emit test_generated event."""
        from src.audit.schemas import AuditEventType

        agent, mock_audit = self._create_agent_with_mock_audit()

        agent._emit_audit_event(
            AuditEventType.TEST_GENERATED,
            {"test_name": "test_example", "cycle": 1}
        )

        mock_audit.emit_simple.assert_called_once()
        call_args = mock_audit.emit_simple.call_args
        assert call_args.kwargs["event_type"] == AuditEventType.TEST_GENERATED

    def test_emits_implementation_generated_event(self):
        """Should emit implementation_generated event."""
        from src.audit.schemas import AuditEventType

        agent, mock_audit = self._create_agent_with_mock_audit()

        agent._emit_audit_event(
            AuditEventType.IMPLEMENTATION_GENERATED,
            {"file": "example.py", "cycle": 1}
        )

        mock_audit.emit_simple.assert_called_once()
        call_args = mock_audit.emit_simple.call_args
        assert call_args.kwargs["event_type"] == AuditEventType.IMPLEMENTATION_GENERATED

    def test_emits_cycle_completed_event(self):
        """Should emit cycle_completed event."""
        from src.audit.schemas import AuditEventType

        agent, mock_audit = self._create_agent_with_mock_audit()

        agent._emit_audit_event(
            AuditEventType.CYCLE_COMPLETED,
            {"cycle": 1, "success": True, "bullets_learned": 2}
        )

        mock_audit.emit_simple.assert_called_once()
        call_args = mock_audit.emit_simple.call_args
        assert call_args.kwargs["event_type"] == AuditEventType.CYCLE_COMPLETED

    def test_emits_pattern_learned_event(self):
        """Should emit pattern_learned event."""
        from src.audit.schemas import AuditEventType

        agent, mock_audit = self._create_agent_with_mock_audit()

        agent._emit_audit_event(
            AuditEventType.PATTERN_LEARNED,
            {"pattern_id": "ctx-001", "content_hash": "abc123"}
        )

        mock_audit.emit_simple.assert_called_once()
        call_args = mock_audit.emit_simple.call_args
        assert call_args.kwargs["event_type"] == AuditEventType.PATTERN_LEARNED

    def test_includes_actor_id(self):
        """Should include agent ID as actor."""
        from src.audit.schemas import AuditEventType

        agent, mock_audit = self._create_agent_with_mock_audit()

        agent._emit_audit_event(AuditEventType.TEST_GENERATED, {})

        call_args = mock_audit.emit_simple.call_args
        assert "tdd-agent" in call_args.kwargs["actor_id"]

    def test_includes_playbook_id(self):
        """Should include playbook ID in event."""
        from src.audit.schemas import AuditEventType

        agent, mock_audit = self._create_agent_with_mock_audit()

        agent._emit_audit_event(AuditEventType.TEST_GENERATED, {})

        call_args = mock_audit.emit_simple.call_args
        assert call_args.kwargs["playbook_id"] == "test-playbook"

    def test_payload_passed_correctly(self):
        """Should pass payload to audit client."""
        from src.audit.schemas import AuditEventType

        agent, mock_audit = self._create_agent_with_mock_audit()

        payload = {"test_name": "test_add", "cycle": 3, "file": "test_math.py"}
        agent._emit_audit_event(AuditEventType.TEST_GENERATED, payload)

        call_args = mock_audit.emit_simple.call_args
        assert call_args.kwargs["payload"] == payload
