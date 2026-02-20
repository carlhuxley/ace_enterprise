"""Test redundancy pre-check integration in AutonomousTDDAgent."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


class TestTDDAgentRedundancyIntegration:
    """Test that redundancy checker is integrated into TDD agent."""

    def test_agent_has_redundancy_checker(self):
        """Agent should have redundancy_checker attribute after init."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent
        from src.agents.redundancy_checker import RedundancyPreChecker

        # Mock dependencies
        mock_ensemble = MagicMock()
        mock_ensemble.models = [("mock", "model", None)]
        mock_ensemble.playbook_manager = MagicMock()
        mock_ensemble.playbook_id = "test"

        mock_reviewer = MagicMock()

        with patch('src.agents.autonomous_tdd_agent.LLMClient'):
            with patch('src.playbook.retrieval.BulletRetriever'):
                agent = AutonomousTDDAgent(
                    ensemble_learner=mock_ensemble,
                    test_reviewer=mock_reviewer,
                    project_root=Path("/tmp/test"),
                    test_dir=Path("/tmp/test/tests"),
                    src_dir=Path("/tmp/test/src"),
                )

        assert hasattr(agent, 'redundancy_checker')
        assert isinstance(agent.redundancy_checker, RedundancyPreChecker)

    def test_build_existing_tests_list_empty(self):
        """Should return empty list when no tests exist."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        mock_ensemble = MagicMock()
        mock_ensemble.models = [("mock", "model", None)]
        mock_ensemble.playbook_manager = MagicMock()
        mock_ensemble.playbook_id = "test"

        with patch('src.agents.autonomous_tdd_agent.LLMClient'):
            with patch('src.playbook.retrieval.BulletRetriever'):
                agent = AutonomousTDDAgent(
                    ensemble_learner=mock_ensemble,
                    test_reviewer=MagicMock(),
                    project_root=Path("/tmp/test"),
                    test_dir=Path("/tmp/test/tests"),
                    src_dir=Path("/tmp/test/src"),
                )

        result = agent._build_existing_tests_list()
        assert result == []
