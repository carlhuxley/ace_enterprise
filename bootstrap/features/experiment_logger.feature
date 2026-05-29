Feature: Experiment Logger
  Logs TDD cycle and ML experiment results for analysis and learning

  Scenario: Log a successful TDD cycle returns an experiment ID
    Given an ExperimentLogger instance
    When a TDD cycle is logged with requirement "Add user authentication" at cycle 1 with green_passed true
    Then a non-empty experiment ID is returned

  Scenario: Log a failed TDD cycle records failure result
    Given an ExperimentLogger instance
    When a TDD cycle is logged with requirement "Handle edge case" at cycle 5 with green_passed false
    Then the logged result indicates failure

  Scenario: Get recent experiments with filter returns matching records
    Given an ExperimentLogger with 3 successful and 2 failed cycles logged
    When recent experiments are retrieved with a success filter and limit 10
    Then 3 records are returned
    And all records indicate success

  Scenario: Unavailable storage is handled gracefully
    Given an ExperimentLogger with no available storage backend
    When a TDD cycle is logged
    Then no exception is raised
    And the return value is None

  Scenario: Get experiment stats returns total count
    Given an ExperimentLogger with 4 experiments logged
    When experiment stats are requested
    Then the total_experiments count is 4
