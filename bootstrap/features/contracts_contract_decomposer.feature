Feature: Contract Decomposer
  As a caller of ContractDecomposer
  I want to turn natural language requirements into structured function contracts
  So that they can be executed via TDD

  Background:
    Given a ContractDecomposer with default configuration
    And an LLM client has been set via set_llm_client that returns a canned response

  Scenario: Decomposing a requirement with a well-formed JSON code block
    Given the LLM client's response contains a markdown code block with a JSON array of one contract:
      """
      [
        {
          "id": "task-001",
          "function_name": "add_numbers",
          "signature": "(a: int, b: int) -> int",
          "docstring": "Add two integers",
          "complexity": 1,
          "test_cases": [
            {"name": "test_add", "input": "(2, 3)", "expected": "5"}
          ]
        }
      ]
      """
    When I call decompose with the requirement "Write a function that adds two numbers"
    Then the call returns a list containing one contract
    And the contract's function_name is "add_numbers"
    And the contract's complexity is 1
    And the contract has one test case named "test_add" with input "(2, 3)" and expected "5"

  Scenario: Decomposing a requirement with a raw JSON array and no code fences
    Given the LLM client's response is the raw text:
      """
      [{"function_name": "subtract", "test_cases": [{"name": "t1", "input": "(5, 2)", "expected": "3"}]}]
      """
    When I call decompose with the requirement "Write a subtraction function"
    Then the call returns a list containing one contract
    And the contract's function_name is "subtract"
    And the contract's id defaults to "subtract-001"
    And the contract's signature defaults to "()"

  Scenario: LLM response contains no JSON array
    Given the LLM client's response is the raw text "Sorry, I cannot help with that."
    When I call decompose with the requirement "Write a function that adds two numbers"
    Then a DecompositionError is raised

  Scenario: A generated contract is missing the required function_name field
    Given the LLM client's response contains a JSON array with one contract missing "function_name"
    When I call decompose with the requirement "Write some function"
    Then a DecompositionError is raised

  Scenario: A generated contract is missing test cases under default configuration
    Given the LLM client's response contains a JSON array with one contract that has no "test_cases"
    When I call decompose with the requirement "Write some function"
    Then a DecompositionError is raised

  Scenario: A contract without test cases is accepted when require_test_cases is disabled
    Given a ContractDecomposer configured with require_test_cases set to False
    And the LLM client's response contains a JSON array with one contract that has no "test_cases"
    When I call decompose with the requirement "Write some function"
    Then the call returns a list containing one contract
    And the contract's test_cases list is empty

  Scenario: A generated contract has an out-of-range complexity value
    Given the LLM client's response contains a JSON array with one contract whose "complexity" is 7
    When I call decompose with the requirement "Write a complex function"
    Then a DecompositionError is raised

  Scenario: LLM produces an empty contract array
    Given the LLM client's response contains the JSON array "[]"
    When I call decompose with the requirement "Write a function that does nothing useful"
    Then a DecompositionError is raised