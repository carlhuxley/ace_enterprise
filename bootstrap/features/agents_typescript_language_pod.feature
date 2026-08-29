Feature: TypeScriptLanguagePod TDD cycle execution

  Scenario: Red phase generates a failing test and persists it to disk
    Given a PodSpec with implementation_file "calculator.py" and test_file "test_calculator.py"
    And the worker agent generates valid TypeScript test code for the spec
    And the orchestrator reports the test run failed as expected
    When run_red is called with the spec
    Then the returned PhaseResult has passed equal to False
    And the test code is written to "calculator.test.ts" on disk

  Scenario: Red phase does not persist the test file when a security breach occurs
    Given a PodSpec with implementation_file "calculator.ts" and test_file "calculator.test.ts"
    And the worker agent generates test code for the spec
    And the orchestrator raises a security breach when running the test
    When run_red is called with the spec
    Then the returned PhaseResult has passed equal to False
    And the error message starts with "SecurityBreach:"
    And no file is written to "calculator.test.ts"

  Scenario: Green phase writes the implementation file only when tests pass
    Given a PodSpec with implementation_file "calculator.ts" and test_file "calculator.test.ts"
    And an existing test file on disk
    And the worker agent generates implementation code that satisfies the test
    And the orchestrator reports the test run passed
    When run_green is called with the spec
    Then the returned PhaseResult has passed equal to True
    And the implementation code is written to "calculator.ts" on disk

  Scenario: Green phase leaves the implementation file untouched when tests still fail
    Given a PodSpec with implementation_file "calculator.ts" and test_file "calculator.test.ts"
    And a pre-existing working implementation already on disk
    And the worker agent generates implementation code that does not satisfy the test
    And the orchestrator reports the test run failed
    When run_green is called with the spec
    Then the returned PhaseResult has passed equal to False
    And the file "calculator.ts" on disk is unchanged from before the call

  Scenario: Refactor phase discards a broken refactor to protect the working implementation
    Given a PodSpec with implementation_file "calculator.ts" and test_file "calculator.test.ts"
    And a working implementation already committed to disk
    And the worker agent generates refactored code that breaks the tests
    And the orchestrator reports the test run failed
    When run_refactor is called with the spec
    Then the returned PhaseResult has passed equal to False
    And the file "calculator.ts" on disk still contains the original working implementation

  Scenario: Refactor phase commits the refactored code when tests still pass
    Given a PodSpec with implementation_file "calculator.ts" and test_file "calculator.test.ts"
    And a working implementation already committed to disk
    And the worker agent generates refactored code that keeps the tests passing
    And the orchestrator reports the test run passed
    When run_refactor is called with the spec
    Then the returned PhaseResult has passed equal to True
    And the file "calculator.ts" on disk contains the refactored code

  Scenario: Python-style file paths in the spec are normalised to TypeScript conventions
    Given a PodSpec with implementation_file "widget.py" and test_file "test_widget.py"
    And the worker agent generates valid TypeScript test code for the spec
    And the orchestrator reports the test run failed as expected
    When run_red is called with the spec
    Then the test code is written to "widget.test.ts" on disk
    And no file named "test_widget.py" or "widget.py" is created

  Scenario: Token usage accumulates per cycle across phases
    Given a PodSpec with cycle_number 3
    And the worker agent's underlying LLM client reports prompt_tokens 120 and completion_tokens 45 for a single call
    When run_red is called with the spec
    Then token_usage returns a list containing one entry for cycle_number 3
    And that entry has input_tokens equal to 120 and output_tokens equal to 45