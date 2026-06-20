Feature: Module TDD Builder

  Scenario: Build a simple module with one function successfully
    Given a ModuleContract with id "simple-001" and name "Calculator"
    And the contract has shared state "result = 0"
    And the contract has one function "add" with signature "(a: int, b: int) -> int"
    And the function has docstring "Add two numbers and return result"
    And the LLM client returns valid Python code for the function
    When I call buildModule with the contract
    Then the ModuleBuildResult has success True
    And the moduleCode contains the shared state definition
    And the moduleCode contains the function implementation
    And the functionResults list has 1 entry
    And the first function result has success True
    And the first function result has tddCycles at least 1
    And the totalCycles equals the sum of all function tddCycles

  Scenario: Build module with multiple functions
    Given a ModuleContract with id "multi-001" and 3 functions
    And each function has a valid signature and docstring
    And the LLM client returns valid code for each function
    When I call buildModule with the contract
    Then the ModuleBuildResult has success True
    And the functionResults list has 3 entries
    And all function results have success True
    And the moduleCode contains all 3 function implementations

  Scenario: Function fails validation after max attempts
    Given a ModuleContract with id "fail-001" and one function "broken"
    And the LLM client returns invalid Python syntax on all attempts
    And maxAttemptsPerFunction is set to 3
    When I call buildModule with the contract
    Then the ModuleBuildResult has success False
    And the error message contains "Failed to build function broken"
    And the first function result has success False
    And the first function result has tddCycles equal to 3
    And the moduleCode does not contain the broken function

  Scenario: Integration tests fail after successful function builds
    Given a ModuleContract with id "integ-001" and 2 functions
    And the contract has 2 integration tests
    And the LLM client returns valid code for all functions
    And the integration tests fail when executed against the module
    When I call buildModule with the contract
    Then the ModuleBuildResult has success False
    And all functionResults have success True
    And the integrationTestResults contains 2 entries
    And at least one integration test result is False
    And the error message contains "Integration tests failed"

  Scenario: Audit events are emitted when audit client is provided
    Given a ModuleContract with id "audit-001" and one function
    And an audit client is configured
    And a sessionId "session-123" is provided
    And the LLM client returns valid code
    When I call buildModule with the contract and sessionId
    Then the ModuleBuildResult has success True
    And an audit event of type CYCLE_COMPLETED is emitted for the function
    And the function audit event contains contractId "audit-001"
    And the function audit event contains the sessionId "session-123"
    And an audit event of type CYCLE_COMPLETED is emitted for the module
    And the module audit event contains totalCycles count

  Scenario: Factory function creates builder with audit disabled
    Given environment variable AUDIT_DISABLED is set to "true"
    When I call createTddBuilderFromConfig with provider "togetherai" and model "test-model"
    Then a ModuleTDDBuilder is returned
    And the builder has no audit client configured
    And the builder modelId is "togetherai-test-model"

  Scenario: Actual model used is tracked in function results
    Given a ModuleContract with id "model-001" and one function
    And the LLM client returns response with actualModel "gpt-4" and provider "openai"
    When I call buildModule with the contract
    Then the first function result has actualModel "gpt-4"
    And the first function result has provider "openai"
    And the audit event contains actualModel "gpt-4"

  Scenario: Function retries on validation failure then succeeds
    Given a ModuleContract with id "retry-001" and one function "calculate"
    And the LLM client returns invalid code on first attempt
    And the LLM client returns valid code on second attempt
    When I call buildModule with the contract
    Then the ModuleBuildResult has success True
    And the first function result has tddCycles equal to 2
    And the first function result has success True