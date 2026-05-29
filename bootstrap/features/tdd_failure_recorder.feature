Feature: TDD Failure Recorder
  Records TDD failures with unique identifiers and tracks intervention statistics

  Scenario: Record a failure returns a non-empty identifier
    Given a failure recorder is created
    When a failure is recorded with requirement "Add user authentication" at cycle 3 with error "NameError: User not defined"
    Then the returned identifier is a non-empty string

  Scenario: Failed cycles counter increments on each recorded failure
    Given a failure recorder is created
    When a failure is recorded with requirement "Calculate tax" at cycle 1 with error "Division by zero"
    And a failure is recorded with requirement "Calculate tax" at cycle 2 with error "TypeError"
    Then the failed cycles count is 2

  Scenario: Reset failed cycles counter returns count to zero
    Given a failure recorder has recorded 2 failures
    When the failed cycles counter is reset
    Then the failed cycles count is 0

  Scenario: Intervention rate is 0.0 when no experiment logger is configured
    Given a failure recorder is created without an experiment logger
    When the intervention rate is requested
    Then the intervention rate is 0.0

  Scenario: Record an intervention for a previously recorded failure
    Given a failure recorder is created
    And a failure was previously recorded with identifier "exp-001"
    When an intervention is recorded for "exp-001" with source "human" and steps "Fixed import statement"
    Then the intervention is accepted without error

  Scenario: Record failure with a suggested fix is accepted
    Given a failure recorder is created
    When a failure is recorded with requirement "Payment processing" at cycle 2 with error "Invalid card" and suggested fix "Validate card format first"
    Then the returned identifier is a non-empty string
    And the failed cycles count is 1
