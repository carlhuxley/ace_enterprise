Feature: Contract Decomposer
  As a user of the contract decomposer
  I want to decompose natural language requirements into function contracts
  So that I can execute them via TDD

  Scenario: Decompose a simple requirement into contracts
    Given a ContractDecomposer instance
    And a mock LLM client that returns valid JSON with one contract
    When I call decompose with requirement "Create a function to add two numbers"
    Then I receive a list containing 1 ContractSpec object
    And the ContractSpec has functionName "add_numbers"
    And the ContractSpec has complexity between 1 and 6

  Scenario: Decompose requirement with multiple functions
    Given a ContractDecomposer instance
    And a mock LLM client that returns JSON with 3 contracts
    When I call decompose with requirement "Create calculator functions"
    Then I receive a list containing 3 ContractSpec objects
    And each ContractSpec has a unique functionName

  Scenario: Handle LLM response with JSON in markdown code block
    Given a ContractDecomposer instance
    And a mock LLM client that returns JSON wrapped in ```json``` code block
    When I call decompose with requirement "Create a greeting function"
    Then I receive a list of ContractSpec objects
    And no DecompositionError is raised

  Scenario: Fail when LLM returns invalid JSON
    Given a ContractDecomposer instance
    And a mock LLM client that returns "This is not JSON"
    When I call decompose with requirement "Create a function"
    Then a DecompositionError is raised with message containing "No JSON array found"

  Scenario: Fail when contract missing required functionName field
    Given a ContractDecomposer instance
    And a mock LLM client that returns JSON with contract missing functionName
    When I call decompose with requirement "Create a function"
    Then a DecompositionError is raised with message containing "function_name"

  Scenario: Fail when contract has invalid complexity value
    Given a ContractDecomposer instance
    And a mock LLM client that returns JSON with complexity 10
    When I call decompose with requirement "Create a function"
    Then a DecompositionError is raised with message containing "Complexity must be 1-6"

  Scenario: Fail when no contracts are generated
    Given a ContractDecomposer instance
    And a mock LLM client that returns an empty JSON array
    When I call decompose with requirement "Create a function"
    Then a DecompositionError is raised with message "No contracts generated"

  Scenario: Configure decomposer with custom settings
    Given a DecomposerConfig with maxTokens 3000 and temperature 0.5
    When I create a ContractDecomposer with this config
    Then the decomposer uses maxTokens 3000 for LLM calls
    And the decomposer uses temperature 0.5 for LLM calls

  Scenario: Set custom LLM client
    Given a ContractDecomposer instance
    And a custom mock LLM client
    When I call setLlmClient with the custom client
    And I call decompose with requirement "Create a function"
    Then the custom LLM client is used for generation

  Scenario: Convert test cases from raw contract to TestCaseSpec
    Given a ContractDecomposer instance
    And a mock LLM client that returns contract with testCases containing name, input, and expected
    When I call decompose with requirement "Create a function"
    Then the returned ContractSpec contains TestCaseSpec objects
    And each TestCaseSpec has name, input, and expected fields

  Scenario: Use default values for optional contract fields
    Given a ContractDecomposer instance
    And a mock LLM client that returns minimal contract with only functionName and testCases
    When I call decompose with requirement "Create a function"
    Then the ContractSpec has default id based on functionName
    And the ContractSpec has default signature "()"
    And the ContractSpec has default complexity 1
    And the ContractSpec has empty hints list