Feature: TDD Failure Recorder
  As a TDD automation system
  I want to record failures, create issues, and track interventions
  So that the system can learn from failures and measure how often manual help is needed

  Scenario: Recording a failure returns a unique experiment identifier
    Given a TDDFailureRecorder with no experiment logger or playbook manager configured
    And a FailureContext with feature_requirement "Add login endpoint", cycle_number 2, and error_message "AssertionError: expected 200 got 500"
    When I call record_failure with that context
    Then the returned experiment ID starts with "tdd-fail-"

  Scenario: Recording a failure creates a persisted bug issue
    Given a TDDFailureRecorder configured with beads_path ".beads/issues.jsonl" pointing to an empty or missing file
    And a FailureContext with feature_requirement "Add login endpoint", cycle_number 1, error_type "ValueError", and error_message "invalid credentials format"
    When I call record_failure with that context
    Then the beads issues file contains a new entry with issue_type "bug", status "open", and title containing "ValueError" and "cycle 1"
    And the new entry's labels include "tdd", "auto-generated", and "valueerror"
    And the new entry's related_experiment matches the returned experiment ID

  Scenario: Recording multiple failures increases the failed cycle count
    Given a newly created TDDFailureRecorder with failed_cycles at 0
    When I call record_failure three times with valid FailureContext objects
    Then the recorder's failed_cycles equals 3

  Scenario: Resetting failed cycles clears the counter
    Given a TDDFailureRecorder that has recorded 2 failures
    When I call reset_failed_cycles
    Then the recorder's failed_cycles equals 0

  Scenario: Recording an intervention updates the matching beads issue
    Given a TDDFailureRecorder whose beads file already contains an issue with related_experiment "tdd-fail-20260101-000000000000"
    And an InterventionRecord with source "human" and steps_taken ["Fixed null check", "Reran tests"]
    When I call record_intervention with experiment_id "tdd-fail-20260101-000000000000" and that intervention record
    Then the matching issue in the beads file now has intervention_source "human"
    And the matching issue's intervention_steps equals ["Fixed null check", "Reran tests"]

  Scenario: Recording an intervention for an unmatched experiment ID leaves existing issues unchanged
    Given a TDDFailureRecorder whose beads file contains an issue with related_experiment "tdd-fail-99999"
    And an InterventionRecord with source "self_healed"
    When I call record_intervention with experiment_id "tdd-fail-does-not-exist" and that intervention record
    Then no issue in the beads file has its intervention_source field set

  Scenario: Calculating intervention rate without an experiment logger returns zero
    Given a TDDFailureRecorder created without an experiment_logger
    When I call calculate_intervention_rate
    Then the returned rate is 0.0

  Scenario: Recording a failure without a playbook manager does not raise an error
    Given a TDDFailureRecorder created without a playbook_manager or playbook_id
    And a FailureContext with feature_requirement "Add logout endpoint", cycle_number 1, and error_message "TimeoutError"
    When I call record_failure with that context
    Then the call completes successfully and returns a valid experiment ID