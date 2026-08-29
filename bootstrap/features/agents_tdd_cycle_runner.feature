Feature: TDD Cycle Runner
  As a caller orchestrating automated TDD workflows
  I want to run a RED -> GREEN -> REFACTOR cycle for a feature
  So that I get back a structured result describing what happened

  Scenario: A fully successful cycle passes through all three phases
    Given a language pod whose RED phase fails as expected with no implementation
    And whose GREEN phase passes on the first attempt
    And whose REFACTOR phase passes
    When I run the cycle for feature requirement "Add a login endpoint"
    Then the returned result has success equal to true
    And the returned result has green_attempts equal to 1
    And the returned result has no error

  Scenario: RED aborts immediately on a security violation without retrying
    Given a language pod whose RED phase fails with error "ForbiddenImport: os.system is not allowed"
    When I run the cycle for feature requirement "Add a file deletion endpoint" with max_red_attempts set to 3
    Then the returned result has success equal to false
    And the returned result error contains "RED aborted"
    And the pod's RED phase was invoked exactly 1 time

  Scenario: RED is retried when it fails before ever writing a test file
    Given a language pod whose RED phase fails twice with empty output and error "malformed markdown fence" then succeeds with a failing test on the third attempt
    When I run the cycle for feature requirement "Add password hashing" with max_red_attempts set to 3
    Then the pod's RED phase was invoked exactly 3 times
    And the returned result has success equal to false only if GREEN was never reached
    And the returned result's red_result reflects the third attempt's outcome

  Scenario: GREEN is retried with error feedback until it passes
    Given a language pod whose RED phase fails as expected with no implementation
    And whose GREEN phase fails with output "AssertionError: expected 200 got 500" on the first attempt and passes on the second attempt
    When I run the cycle for feature requirement "Add a health check endpoint" with max_green_attempts set to 3
    Then the returned result has green_attempts equal to 2
    And the second GREEN attempt was given error_output "AssertionError: expected 200 got 500"

  Scenario: GREEN failure after exhausting all retries produces an unsuccessful result
    Given a language pod whose RED phase fails as expected with no implementation
    And whose GREEN phase always fails with error "AssertionError: expected 200 got 500"
    When I run the cycle for feature requirement "Add a broken endpoint" with max_green_attempts set to 3
    Then the returned result has success equal to false
    And the returned result has green_attempts equal to 3
    And the returned result error equals "AssertionError: expected 200 got 500"

  Scenario: GREEN aborts immediately on a security breach without retrying
    Given a language pod whose RED phase fails as expected with no implementation
    And whose GREEN phase fails with error "SecurityBreach: attempted network access"
    When I run the cycle for feature requirement "Add an unsafe data export"
    Then the returned result has success equal to false
    And the pod's GREEN phase was invoked exactly 1 time

  Scenario: A cycle where GREEN passes but REFACTOR fails is reported as unsuccessful
    Given a language pod whose RED phase fails as expected with no implementation
    And whose GREEN phase passes on the first attempt
    And whose REFACTOR phase fails with error "lint check failed"
    When I run the cycle for feature requirement "Add a search endpoint"
    Then the returned result has success equal to false
    And the returned result error equals "lint check failed"
    And the returned result's green_result has passed equal to true

  Scenario: Token usage accumulated during the cycle is included in the result
    Given a language pod that records token usage on every phase call
    And whose RED phase fails as expected with no implementation
    And whose GREEN phase passes on the first attempt
    And whose REFACTOR phase passes
    When I run the cycle for feature requirement "Add a profile page"
    Then the returned result's token_usage contains an entry for each pod call made during the cycle