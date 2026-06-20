Feature: TDD Cycle Analyzer

  Scenario: Calculate first-pass rate when no cycles exist
    Given an experiment logger with no TDD cycle records
    When I request the first-pass rate
    Then the first-pass rate should be 0.0

  Scenario: Calculate first-pass rate with all first-pass successes
    Given an experiment logger with TDD cycle records:
      | result  | retryCount |
      | SUCCESS | 0           |
      | SUCCESS | 0           |
      | SUCCESS | 0           |
    When I request the first-pass rate
    Then the first-pass rate should be 1.0

  Scenario: Calculate first-pass rate with mixed retry counts
    Given an experiment logger with TDD cycle records:
      | result  | retryCount |
      | SUCCESS | 0           |
      | SUCCESS | 1           |
      | SUCCESS | 0           |
      | FAILURE | 0           |
      | SUCCESS | 2           |
    When I request the first-pass rate
    Then the first-pass rate should be 0.4

  Scenario: Filter first-pass rate by playbook ID
    Given an experiment logger with TDD cycle records:
      | playbookId | result  | retryCount |
      | playbook-A  | SUCCESS | 0           |
      | playbook-A  | SUCCESS | 1           |
      | playbook-B  | SUCCESS | 0           |
      | playbook-B  | SUCCESS | 0           |
    When I request the first-pass rate for playbook "playbook-B"
    Then the first-pass rate should be 1.0

  Scenario: Filter first-pass rate by time range
    Given an experiment logger with TDD cycle records:
      | timestamp           | result  | retryCount |
      | 2024-01-01 10:00:00 | SUCCESS | 0           |
      | 2024-01-05 10:00:00 | SUCCESS | 1           |
      | 2024-01-10 10:00:00 | SUCCESS | 0           |
      | 2024-01-15 10:00:00 | SUCCESS | 0           |
    When I request the first-pass rate since "2024-01-08 00:00:00"
    Then the first-pass rate should be 1.0

  Scenario: Calculate trend with no cycles
    Given an experiment logger with no TDD cycle records
    When I request the trend with 5 periods of 7 days each
    Then the trend should contain 0 periods

  Scenario: Calculate trend with cycles in multiple periods
    Given the current time is "2024-02-15 12:00:00"
    And an experiment logger with TDD cycle records:
      | timestamp           | result  | retryCount |
      | 2024-02-01 10:00:00 | SUCCESS | 0           |
      | 2024-02-02 10:00:00 | SUCCESS | 1           |
      | 2024-02-03 10:00:00 | SUCCESS | 0           |
      | 2024-02-10 10:00:00 | SUCCESS | 0           |
      | 2024-02-11 10:00:00 | FAILURE | 0           |
      | 2024-02-12 10:00:00 | SUCCESS | 0           |
    When I request the trend with 3 periods of 7 days each
    Then the trend should contain 2 periods
    And period 1 should span from "2024-02-01 12:00:00" to "2024-02-08 12:00:00"
    And period 1 should have 3 total cycles
    And period 1 should have 2 first-pass cycles
    And period 1 should have a first-pass rate of 0.6666666666666666
    And period 2 should span from "2024-02-08 12:00:00" to "2024-02-15 12:00:00"
    And period 2 should have 3 total cycles
    And period 2 should have 2 first-pass cycles
    And period 2 should have a first-pass rate of 0.6666666666666666

  Scenario: Calculate trend filtered by playbook ID
    Given the current time is "2024-03-10 12:00:00"
    And an experiment logger with TDD cycle records:
      | timestamp           | playbookId | result  | retryCount |
      | 2024-03-01 10:00:00 | playbook-X  | SUCCESS | 0           |
      | 2024-03-02 10:00:00 | playbook-Y  | SUCCESS | 1           |
      | 2024-03-05 10:00:00 | playbook-X  | SUCCESS | 0           |
    When I request the trend for playbook "playbook-X" with 2 periods of 7 days each
    Then the trend should contain 1 period
    And period 1 should have 2 total cycles
    And period 1 should have 2 first-pass cycles
    And period 1 should have a first-pass rate of 1.0