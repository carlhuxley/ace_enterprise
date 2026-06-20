Feature: Contract-driven agent orchestration

  Scenario: Register a new contract
    Given a contract with ID "calc_001" for function "calculate_tax"
    When the contract is registered with the orchestrator
    And I check the contract status for "calc_001"
    Then the status should be "pending"

  Scenario: Generate implementation prompt from contract
    Given a contract with ID "calc_002" for function "add_numbers"
    And the function signature is "(a: int, b: int) -> int"
    And the docstring is "Add two numbers together"
    And test case "basic_add" with input "(2, 3)" expecting "5"
    And test case "negative_add" with input "(-1, 1)" expecting "0"
    And hints include "Use the + operator"
    When the contract is registered
    And I get the implementation prompt for "calc_002"
    Then the prompt should contain "def add_numbers(a: int, b: int) -> int:"
    And the prompt should contain "Add two numbers together"
    And the prompt should contain "basic_add: (2, 3) should return 5"
    And the prompt should contain "Use the + operator"

  Scenario: Submit valid implementation that passes all tests
    Given a contract with ID "calc_003" for function "multiply"
    And the function signature is "(x: int, y: int) -> int"
    And test case "test_positive" with input "(3, 4)" expecting "12"
    And test case "test_zero" with input "(5, 0)" expecting "0"
    And the contract is registered
    When I submit implementation code "def multiply(x: int, y: int) -> int:\n    return x * y"
    Then the implementation status should be "validated"
    And test result "test_positive" should be True
    And test result "test_zero" should be True
    And the contract status for "calc_003" should be "validated"

  Scenario: Submit implementation with syntax error
    Given a contract with ID "calc_004" for function "divide"
    And the function signature is "(a: float, b: float) -> float"
    And test case "test_div" with input "(10.0, 2.0)" expecting "5.0"
    And the contract is registered
    When I submit implementation code "def divide(a: float, b: float) -> float\n    return a / b"
    Then the implementation status should be "failed"
    And the implementation error should contain "Syntax error"

  Scenario: Submit implementation that fails test cases
    Given a contract with ID "calc_005" for function "subtract"
    And the function signature is "(a: int, b: int) -> int"
    And test case "test_sub" with input "(10, 3)" expecting "7"
    And the contract is registered
    When I submit implementation code "def subtract(a: int, b: int) -> int:\n    return a + b"
    Then the implementation status should be "failed"
    And test result "test_sub" should be False

  Scenario: Submit implementation for non-existent contract
    Given no contract with ID "missing_001" exists
    When I attempt to submit implementation code "def foo(): pass" for contract "missing_001"
    Then a ValueError should be raised with message "Contract missing_001 not found"

  Scenario: Validate implementation with fixture setup and teardown
    Given a contract with ID "calc_006" for function "get_counter"
    And the function signature is "() -> int"
    And fixture setup code "counter = 0"
    And test case "test_counter" with input "()" expecting "0"
    And the contract is registered
    When I submit implementation code "def get_counter() -> int:\n    return counter"
    Then the implementation status should be "validated"
    And test result "test_counter" should be True

  Scenario: Track agent reference in implementation
    Given a contract with ID "calc_007" for function "square"
    And the function signature is "(n: int) -> int"
    And test case "test_square" with input "(4)" expecting "16"
    And the contract is registered
    When I submit implementation code "def square(n: int) -> int:\n    return n * n" with agent reference "agent_small_model_1"
    Then the implementation agent reference should be "agent_small_model_1"
    And the implementation status should be "validated"