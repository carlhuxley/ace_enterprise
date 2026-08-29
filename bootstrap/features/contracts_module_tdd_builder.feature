Feature: Module TDD Builder generates and validates module implementations from contracts

  Scenario: Successfully building a module where all functions pass validation and integration tests
    Given a module contract "calc-utils-001" with function "add_numbers" and integration test "test_add_numbers_returns_sum"
    And the language model returns valid code for "add_numbers" on the first attempt
    And the integration test "test_add_numbers_returns_sum" passes against the assembled module
    When the module is built
    Then the build result reports success as true
    And the build result's total cycles equal 1
    And the module code contains the implementation of "add_numbers"
    And the integration test result for "test_add_numbers_returns_sum" is true

  Scenario: A function fails validation on every attempt, causing the module build to fail
    Given a module contract "calc-utils-002" with function "divide_numbers" and a maximum of 2 attempts per function
    And the language model returns invalid code for "divide_numbers" on every attempt
    When the module is built
    Then the build result reports success as false
    And the build result's error message mentions "Failed to build function divide_numbers"
    And the integration test results are empty

  Scenario: A function requires a retry before producing valid code
    Given a module contract "calc-utils-003" with function "multiply_numbers" and a maximum of 3 attempts per function
    And the language model returns invalid code for "multiply_numbers" on the first attempt
    And the language model returns valid code for "multiply_numbers" on the second attempt
    When the module is built
    Then the function build result for "multiply_numbers" reports success as true
    And the function build result for "multiply_numbers" reports 2 tdd cycles

  Scenario: All functions build successfully but an integration test fails
    Given a module contract "calc-utils-004" with function "subtract_numbers" and integration test "test_subtract_numbers_returns_difference"
    And the language model returns valid code for "subtract_numbers" on the first attempt
    And the integration test "test_subtract_numbers_returns_difference" fails against the assembled module
    When the module is built
    Then the build result reports success as false
    And the build result's error message mentions "Integration tests failed"
    And the integration test result for "test_subtract_numbers_returns_difference" is false

  Scenario: Building a module emits an audit event recording the actual model used for each function
    Given a module contract "calc-utils-005" with function "average_numbers"
    And an audit client is attached to the builder
    And the language model returns valid code for "average_numbers" using actual model "claude-3-opus" and provider "anthropic"
    When the module is built
    Then an audit event of type "CYCLE_COMPLETED" is emitted with actor id "claude-3-opus"
    And the audit event payload includes provider "anthropic"

  Scenario: Creating a TDD builder from configuration with audit enabled
    Given provider "togetherai" and model "llama-3-70b" configuration values
    When a TDD builder is created from this configuration
    Then the returned builder is configured with model id "togetherai-llama-3-70b"