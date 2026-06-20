Feature: Project-aware TDD module for intelligent file placement and code reuse

  Scenario: Get folder for a recognized keyword
    Given a ProjectStructure instance
    When I call get_folder_for_keyword with "broker"
    Then the result should be "src/broker"

  Scenario: Get folder for keyword with different casing
    Given a ProjectStructure instance
    When I call get_folder_for_keyword with "AGENT"
    Then the result should be "src/agents"

  Scenario: Get folder for unrecognized keyword
    Given a ProjectStructure instance
    When I call get_folder_for_keyword with "unknown"
    Then the result should be None

  Scenario: Determine file placement based on feature requirement containing routing keyword
    Given a ProjectStructure instance
    When I call determine_file_placement with "Implement routing logic for message distribution"
    Then the result should be "src/broker"

  Scenario: Determine file placement based on feature requirement containing storage keyword
    Given a ProjectStructure instance
    When I call determine_file_placement with "Add persistence layer for user data"
    Then the result should be "src/storage"

  Scenario: Determine file placement for feature with no matching keywords
    Given a ProjectStructure instance
    When I call determine_file_placement with "Implement general business logic"
    Then the result should be "src"

  Scenario: Get cached architecture on first call
    Given a ProjectArchitecture instance
    When I call get_architecture
    Then the result should be a dictionary

  Scenario: Get cached architecture on subsequent call
    Given a ProjectArchitecture instance
    When I call get_architecture twice
    Then both results should be the same dictionary instance

  Scenario: Get project structure with folder information
    Given a ProjectArchitecture instance
    When I call get_structure
    Then the result should be a ProjectStructure instance
    And it should contain a folder "src/broker" with purpose "routing and orchestration"
    And it should contain a folder "src/agents" with purpose "autonomous agents"
    And it should contain a folder "src/storage" with purpose "persistence layer"
    And it should contain a folder "src/utils" with purpose "shared utilities"

  Scenario: Find utilities for a capability with no matches
    Given a CodeReuseDetector instance
    When I call find_utilities with "LLM generation"
    Then the result should be an empty list

  Scenario: Find base classes for a class type
    Given a CodeReuseDetector instance
    When I call find_base_classes with "agent"
    Then the result should be a list

  Scenario: Suggest imports for feature requiring LLM
    Given a CodeReuseDetector instance
    When I call suggest_imports with "Create a feature using LLM for text generation"
    Then the result should contain "from src.utils.llm_client import LLMClient"

  Scenario: Suggest imports for feature requiring embedding
    Given a CodeReuseDetector instance
    When I call suggest_imports with "Implement embedding service for vector search"
    Then the result should contain "from src.utils.embedding import EmbeddingService"

  Scenario: Suggest imports for feature requiring playbook
    Given a CodeReuseDetector instance
    When I call suggest_imports with "Access playbook data from storage"
    Then the result should contain "from src.storage.repository import PlaybookRepository"

  Scenario: Suggest imports for feature requiring base agent
    Given a CodeReuseDetector instance
    When I call suggest_imports with "Create a new agent extending base functionality"
    Then the result should contain "from src.agents.base import BaseAgent"

  Scenario: Suggest no imports for unrecognized feature
    Given a CodeReuseDetector instance
    When I call suggest_imports with "Implement generic business logic"
    Then the result should be an empty list

  Scenario: Extract explicit constraints with new class pattern
    Given a Gherkin content with "Background: Given a new DynamicModelRouter class to be created in src/broker/dynamic_model_router.py"
    When I call extract_explicit_constraints with this content
    Then the result should be a dictionary with "class_name" as "DynamicModelRouter"
    And the result should have "file_path" as "src/broker/dynamic_model_router.py"

  Scenario: Extract explicit constraints with create pattern
    Given a Gherkin content with "Background: Given create a UserService in src/services/user_service.py"
    When I call extract_explicit_constraints with this content
    Then the result should be a dictionary with "class_name" as "UserService"
    And the result should have "file_path" as "src/services/user_service.py"

  Scenario: Extract explicit constraints with should be placed pattern
    Given a Gherkin content with "Background: Given PaymentProcessor should be placed in src/payment/processor.py"
    When I call extract_explicit_constraints with this content
    Then the result should be a dictionary with "class_name" as "PaymentProcessor"
    And the result should have "file_path" as "src/payment/processor.py"

  Scenario: Extract explicit constraints with no matching pattern
    Given a Gherkin content with "Background: Given some other context without class specification"
    When I call extract_explicit_constraints with this content
    Then the result should be an empty dictionary