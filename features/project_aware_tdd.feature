Feature: Project-aware TDD agent with code reuse detection
  As a developer using ACE
  I want the TDD agent to understand project structure
  So that files are placed correctly and existing code is reused

  Background:
    Given a project with existing structure:
      | folder       | purpose                    |
      | src/broker   | routing and orchestration  |
      | src/agents   | autonomous agents          |
      | src/storage  | persistence layer          |
      | src/utils    | shared utilities           |

  Scenario: Analyze project structure before code generation
    Given a codebase with indexed knowledge graph
    When the TDD agent starts a new feature build
    Then it should query get_architecture to understand folder layout
    And it should cache the structure for the session
    And the structure map should include folder purposes

  Scenario: Route new broker code to correct directory
    Given a feature requirement "Add cost-quality analyzer for routing"
    When the TDD agent determines file placement
    Then the implementation file should be in "src/broker/"
    And the test file should be in "tests/"
    And the file should not be placed in "src/" root

  Scenario: Route new agent code to correct directory
    Given a feature requirement "Add project analyzer agent"
    When the TDD agent determines file placement
    Then the implementation file should be in "src/agents/"

  Scenario: Detect reusable utilities before implementation
    Given an existing utility "src/utils/llm_client.py" with LLMClient class
    And a feature requirement that needs LLM generation
    When the TDD agent plans the implementation
    Then it should search_graph for existing LLM utilities
    And it should suggest importing LLMClient instead of recreating
    And the generated code should include "from src.utils.llm_client import LLMClient"

  Scenario: Find base classes to extend
    Given an existing base class "BaseAgent" in "src/agents/base.py"
    And a feature requirement "Add new specialized agent"
    When the TDD agent generates implementation
    Then it should find BaseAgent via search_graph
    And suggest extending it rather than creating standalone class

  Scenario: Match project naming conventions
    Given existing code uses snake_case for functions
    And existing code uses PascalCase for classes
    And existing code has Google-style docstrings
    When the TDD agent generates new code
    Then function names should be snake_case
    And class names should be PascalCase
    And docstrings should follow Google style

  Scenario: Determine file placement from feature keywords
    Given the following feature-to-folder mappings:
      | keyword      | folder       |
      | broker       | src/broker   |
      | routing      | src/broker   |
      | agent        | src/agents   |
      | storage      | src/storage  |
      | repository   | src/storage  |
      | utility      | src/utils    |
      | helper       | src/utils    |
    When a feature mentions "broker" or "routing"
    Then files should go to "src/broker/"
