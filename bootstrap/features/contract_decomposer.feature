Feature: Contract Decomposer
  As a user of the contract decomposer
  I want to decompose natural language requirements into function contracts
  So that I can execute them via TDD

  Scenario: Decompose a simple requirement into contracts
    Given a ContractDecomposer instance
    And a mock LLM client that returns valid JSON with one contract
    When I call decompose with requirement "Create a function to add two numbers"
    Then I receive a list containing 1 ContractSpec object
    And the ContractSpec has function_name "add_numbers"
    And the ContractSpec has complexity between 1 and 6

  Scenario: Decompose requirement with multiple functions
    Given a ContractDecomposer instance
    And a mock LLM client that returns JSON with 3 contracts
    When I call decompose with requirement "Create calculator functions"
    Then I receive a list containing 3 ContractSpec objects

  Scenario: Handle LLM response with JSON in markdown code block
    Given a ContractDecomposer instance
    And a mock LLM client that returns JSON wrapped in ```json``` code block
    When I call decompose with requirement "Create a greeting function"
    Then I receive a list of ContractSpec objects successfully
    And no DecompositionError is raised

  Scenario: Fail when LLM returns invalid JSON
    Given a ContractDecomposer instance
    And a mock LLM client that returns malformed JSON
    When I call decompose with requirement "Create a function"
    Then a DecompositionError is raised with message containing "Invalid JSON"

  Scenario: Fail when contract missing required function_name field
    Given a ContractDecomposer instance
    And a mock LLM client that returns JSON without function_name field
    When I call decompose with requirement "Create a function"
    Then a DecompositionError is raised with message containing "function_name"

  Scenario: Fail when contract has invalid complexity value
    Given a ContractDecomposer instance
    And a mock LLM client that returns JSON with complexity 10
    When I call decompose with requirement "Create a function"
    Then a DecompositionError is raised with message containing "Complexity must be 1-6"

  Scenario: Fail when no contracts generated
    Given a ContractDecomposer instance
    And a mock LLM client that returns empty JSON array
    When I call decompose with requirement "Create a function"
    Then a DecompositionError is raised with message "No contracts generated"

  Scenario: Use custom configuration for decomposition
    Given a DecomposerConfig with max_tokens 3000 and temperature 0.5
    And a ContractDecomposer instance initialized with that config
    And a mock LLM client that captures generation parameters
    When I call decompose with requirement "Create a function"
    Then the LLM is called with max_tokens 3000
    And the LLM is called with temperature 0.5

  Scenario: Set custom LLM client
    Given a ContractDecomposer instance
    And a custom mock LLM client
    When I call set_llm_client with the custom client
    And I call decompose with requirement "Create a function"
    Then the custom LLM client is used for generation

  Scenario: Convert test cases from raw contract to TestCaseSpec
    Given a ContractDecomposer instance
    And a mock LLM client that returns contract with 2 test cases
    When I call decompose with requirement "Create a function"
    Then I receive a ContractSpec with 2 test_cases
    And each test case has name, input, and expected fields

  Scenario: Handle contract with optional hints field
    Given a ContractDecomposer instance
    And a mock LLM client that returns contract with hints array
    When I call decompose with requirement "Create a complex function"
    Then I receive a ContractSpec with hints populated

  Scenario: Generate default id when not provided
    Given a ContractDecomposer instance
    And a mock LLM client that returns contract without id field
    When I call decompose with requirement "Create a function"
    Then I receive a ContractSpec with id generated from function_name

  Scenario: Require test cases when configuration demands it
    Given a DecomposerConfig with require_test_cases True
    And a ContractDecomposer instance initialized with that config
    And a mock LLM client that returns contract without test_cases
    When I call decompose with requirement "Create a function"
    Then a DecompositionError is raised with message containing "test_cases"