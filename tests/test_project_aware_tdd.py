# Test file for project_aware_tdd
import pytest
from unittest.mock import patch
from src.agents.project_aware_tdd import (
    ProjectArchitecture,
    ProjectStructure,
    TDDTAgent,
    CodeReuseDetector,
    FolderInfo,
    KEYWORD_FOLDER_MAPPINGS,
)


class TestProjectArchitecture:
    """Tests for ProjectArchitecture class."""

    def test_project_architecture_has_get_architecture_method(self):
        project_architecture = ProjectArchitecture()
        assert hasattr(project_architecture, 'get_architecture')

    def test_project_architecture_can_be_created(self):
        project_architecture = ProjectArchitecture()
        assert project_architecture.get_architecture() == {}

    def test_architecture_is_cached_for_session(self):
        """Verify that architecture is fetched only once and then cached."""
        project_architecture = ProjectArchitecture()
        with patch.object(project_architecture, '_fetch_architecture', return_value={'cached': True}) as mock_fetch:
            result1 = project_architecture.get_architecture()
            result2 = project_architecture.get_architecture()
            mock_fetch.assert_called_once()
            assert result1 == result2 == {'cached': True}

    def test_structure_includes_folder_purposes(self):
        """Verify structure contains folder paths with purposes."""
        project_architecture = ProjectArchitecture()
        structure = project_architecture.get_structure()

        assert "src/broker" in structure.folders
        assert structure.folders["src/broker"].purpose == "routing and orchestration"

        assert "src/agents" in structure.folders
        assert structure.folders["src/agents"].purpose == "autonomous agents"


class TestTDDTAgent:
    """Tests for TDDTAgent class."""

    def test_agent_queries_architecture_on_feature_build(self):
        agent = TDDTAgent()
        with patch.object(agent.project_architecture, 'get_architecture') as mock_get_architecture:
            agent.start_feature_build()
            mock_get_architecture.assert_called_once()

    def test_broker_feature_placed_in_broker_folder(self):
        """Scenario: Route new broker code to correct directory."""
        agent = TDDTAgent()
        locations = agent.determine_file_locations("Add cost-quality analyzer for routing")

        assert locations["implementation"] == "src/broker"
        assert locations["test"] == "tests"

    def test_agent_feature_placed_in_agents_folder(self):
        """Scenario: Route new agent code to correct directory."""
        agent = TDDTAgent()
        locations = agent.determine_file_locations("Add project analyzer agent")

        assert locations["implementation"] == "src/agents"

    def test_storage_feature_placed_in_storage_folder(self):
        """Route storage-related code to storage folder."""
        agent = TDDTAgent()
        locations = agent.determine_file_locations("Add repository for playbook persistence")

        assert locations["implementation"] == "src/storage"

    def test_utility_feature_placed_in_utils_folder(self):
        """Route utility code to utils folder."""
        agent = TDDTAgent()
        locations = agent.determine_file_locations("Add helper for JSON parsing")

        assert locations["implementation"] == "src/utils"

    def test_unknown_feature_defaults_to_src(self):
        """Unknown feature types default to src folder."""
        agent = TDDTAgent()
        locations = agent.determine_file_locations("Add something completely new")

        assert locations["implementation"] == "src"


class TestProjectStructure:
    """Tests for ProjectStructure class."""

    def test_keyword_folder_mapping_broker(self):
        structure = ProjectStructure()
        assert structure.get_folder_for_keyword("broker") == "src/broker"
        assert structure.get_folder_for_keyword("routing") == "src/broker"

    def test_keyword_folder_mapping_agent(self):
        structure = ProjectStructure()
        assert structure.get_folder_for_keyword("agent") == "src/agents"

    def test_keyword_folder_mapping_storage(self):
        structure = ProjectStructure()
        assert structure.get_folder_for_keyword("storage") == "src/storage"
        assert structure.get_folder_for_keyword("repository") == "src/storage"

    def test_keyword_folder_mapping_utility(self):
        structure = ProjectStructure()
        assert structure.get_folder_for_keyword("utility") == "src/utils"
        assert structure.get_folder_for_keyword("helper") == "src/utils"


class TestCodeReuseDetector:
    """Tests for CodeReuseDetector class."""

    def test_suggests_llm_client_for_llm_features(self):
        """Scenario: Detect reusable utilities before implementation."""
        detector = CodeReuseDetector()
        suggestions = detector.suggest_imports("Add feature that needs LLM generation")

        assert "from src.utils.llm_client import LLMClient" in suggestions

    def test_suggests_embedding_service_for_embedding_features(self):
        detector = CodeReuseDetector()
        suggestions = detector.suggest_imports("Add embedding-based search")

        assert "from src.utils.embedding import EmbeddingService" in suggestions

    def test_suggests_playbook_repository_for_playbook_features(self):
        detector = CodeReuseDetector()
        suggestions = detector.suggest_imports("Store data in playbook")

        assert "from src.storage.repository import PlaybookRepository" in suggestions

    def test_suggests_base_agent_for_agent_extensions(self):
        """Scenario: Find base classes to extend."""
        detector = CodeReuseDetector()
        suggestions = detector.suggest_imports("Add new specialized agent based on base agent")

        assert "from src.agents.base import BaseAgent" in suggestions

    def test_no_suggestions_for_unrelated_features(self):
        detector = CodeReuseDetector()
        suggestions = detector.suggest_imports("Add simple math calculation")

        assert len(suggestions) == 0


class TestTDDAgentIntegration:
    """Integration tests for TDDTAgent."""

    def test_agent_provides_reuse_suggestions(self):
        agent = TDDTAgent()
        suggestions = agent.get_reuse_suggestions("Add broker with LLM generation")

        assert "from src.utils.llm_client import LLMClient" in suggestions

    def test_full_feature_build_workflow(self):
        """Test complete workflow: architecture query, file placement, reuse."""
        agent = TDDTAgent()

        # Start feature build
        agent.start_feature_build()

        # Determine locations
        feature = "Add cost-quality analyzer for routing with LLM"
        locations = agent.determine_file_locations(feature)
        suggestions = agent.get_reuse_suggestions(feature)

        # Verify broker feature goes to src/broker
        assert locations["implementation"] == "src/broker"
        assert locations["test"] == "tests"

        # Verify LLM import is suggested
        assert any("LLMClient" in s for s in suggestions)


class TestExtractExplicitConstraints:
    """Tests for Gherkin Background constraint extraction."""

    def test_extracts_class_name_with_preserved_casing(self):
        """Verify class name casing is preserved from Gherkin."""
        agent = TDDTAgent()
        gherkin = """
Feature: Dynamic model routing based on cost-quality constraints
  As an ACE user
  I want a DynamicModelRouter class that routes tasks to models

  Background:
    Given an existing CostQualityAnalyzer in src/broker/cost_quality_analyzer.py
    And a new DynamicModelRouter class to be created in src/broker/dynamic_model_router.py
    And test file in tests/test_dynamic_model_router.py

  Scenario: Create DynamicModelRouter with routing modes enum
    Given I need to route model requests based on different strategies
    When I create a RoutingMode enum
    Then it should have values: BEST_QUALITY, BUDGET, BALANCED, PARETO
"""
        constraints = agent.extract_explicit_constraints(gherkin)

        assert constraints.get("class_name") == "DynamicModelRouter"
        assert constraints.get("file_path") == "src/broker/dynamic_model_router.py"

    def test_extracts_constraints_case_insensitive_matching(self):
        """Verify matching works regardless of keyword case in Background."""
        agent = TDDTAgent()
        gherkin = """
Feature: Cost quality analysis
  Background:
    Given A NEW CostQualityAnalyzer CLASS TO BE CREATED IN src/broker/cost_analyzer.py

  Scenario: Analyzer calculates efficiency metrics
    Given a set of model performance data
    When I calculate cost efficiency
    Then the analyzer returns quality-per-dollar scores
"""
        constraints = agent.extract_explicit_constraints(gherkin)

        assert constraints.get("class_name") == "CostQualityAnalyzer"
        assert constraints.get("file_path") == "src/broker/cost_analyzer.py"

    def test_extracts_create_pattern(self):
        """Test pattern 2: create a <Class> in <path>."""
        agent = TDDTAgent()
        gherkin = """
Feature: Model selection for task routing
  Background:
    Given we need to create a ModelSelector in src/agents/model_selector.py

  Scenario: Select best model for code generation
    Given available models with varying capabilities
    When selecting a model for code generation task
    Then the selector chooses a model optimized for coding
"""
        constraints = agent.extract_explicit_constraints(gherkin)

        assert constraints.get("class_name") == "ModelSelector"
        assert constraints.get("file_path") == "src/agents/model_selector.py"

    def test_returns_empty_when_no_constraints(self):
        """Verify empty dict when Background has no explicit class constraints."""
        agent = TDDTAgent()
        gherkin = """
Feature: General configuration management
  Background:
    Given the system is configured with default settings
    And the database connection is established

  Scenario: Load configuration from environment
    Given environment variables are set
    When the application starts
    Then configuration values are loaded from environment
"""
        constraints = agent.extract_explicit_constraints(gherkin)

        assert constraints == {}
