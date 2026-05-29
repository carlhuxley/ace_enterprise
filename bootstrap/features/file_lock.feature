Feature: File Lock and Drift Detection
  Detects inadvertent changes to files outside the intended target set

  Scenario: Drift report with no changed files is clean
    Given a drift report with no drifted files
    When is_clean is checked
    Then it returns true

  Scenario: Drift report with changed files is not clean
    Given a drift report with one drifted file having 5 added lines and 2 removed lines
    When is_clean is checked
    Then it returns false

  Scenario: assert_clean raises an error when drift is detected
    Given a drift report with one drifted file
    When assert_clean is called
    Then an error is raised
    And the error contains the drifted file information

  Scenario: Drift detector finds no drift when no files changed
    Given a drift detector with no changed files reported
    When check is called with a list of allowed target files
    Then the returned drift report is clean

  Scenario: Drift detector detects changes outside the target set
    Given a drift detector where "unexpected.ts" changed with 4 added lines
    And "unexpected.ts" is not in the allowed target files
    When check is called
    Then the drift report is not clean
    And the drift report includes "unexpected.ts"
