Feature: Project-aware TDD file placement, code reuse detection, and constraint extraction

  Scenario: Determine file placement for a broker-related requirement
    Given a ProjectStructure instance
    When determine_file_placement is called with "Implement message routing between agents"
    Then the result is "src/broker"

  Scenario: Determine file placement for a storage-related requirement
    Given a ProjectStructure instance
    When determine_file_placement is called with "Add a new repository for saving playbooks"
    Then the result is "src/storage"

  Scenario: Fall back to default src folder when no keyword matches
    Given a ProjectStructure instance
    When determine_file_placement is called with "Improve error messages in the CLI"
    Then the result is "src"

  Scenario: Look up folder for a known keyword
    Given a ProjectStructure instance
    When get_folder_for_keyword is called with "Helper"
    Then the result is "src/utils"

  Scenario: Look up folder for an unknown keyword
    Given a ProjectStructure instance
    When get_folder_for_keyword is called with "database"
    Then the result is None

  Scenario: Retrieve project structure with known folder purposes
    Given a ProjectArchitecture instance
    When get_structure is called
    Then the result includes a folder "src/agents" with purpose "autonomous agents"
    And the result includes a folder "src/storage" with purpose "persistence layer"

  Scenario: Suggest imports for an LLM generation feature
    Given a CodeReuseDetector instance
    When suggest_imports is called with "Add LLM generation for summaries"
    Then the result includes "from src.utils.llm_client import LLMClient"

  Scenario: Suggest imports for a playbook and base agent feature
    Given a CodeReuseDetector instance
    When suggest_imports is called with "Create a new agent extending the base agent that manages playbooks"
    Then the result includes "from src.storage.repository import PlaybookRepository"
    And the result includes "from src.agents.base import BaseAgent"

  Scenario: Find utilities for an unrecognized capability returns no results
    Given a CodeReuseDetector instance
    When find_utilities is called with "quantum entanglement"
    Then the result is an empty list

  Scenario: Find base classes for a class type returns no results
    Given a CodeReuseDetector instance
    When find_base_classes is called with "repository"
    Then the result is an empty list

  Scenario: Extract explicit constraints from a Background using "a new ... class to be created in ..." phrasing
    Given the Gherkin content:
      """
      Background:
        Given a new DynamicModelRouter class to be created in src/broker/dynamic_model_router.py

      Scenario: Example
        Given something
      """
    When extract_explicit_constraints is called with this content
    Then the result is {"class_name": "DynamicModelRouter", "file_path": "src/broker/dynamic_model_router.py"}

  Scenario: Extract explicit constraints from a Background using "create a ... in ..." phrasing
    Given the Gherkin content:
      """
      Background:
        Given we create a PlaybookRepository in src/storage/playbook_repository.py

      Scenario: Example
        Given something
      """
    When extract_explicit_constraints is called with this content
    Then the result is {"class_name": "PlaybookRepository", "file_path": "src/storage/playbook_repository.py"}

  Scenario: Extract explicit constraints returns empty dict when no pattern matches
    Given the Gherkin content:
      """
      Background:
        Given the system is configured

      Scenario: Example
        Given something
      """
    When extract_explicit_constraints is called with this content
    Then the result is {}