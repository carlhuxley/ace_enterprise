Feature: TDD Cycle Reliability Analysis
  As a caller monitoring TDD workflow health
  I want to measure first-pass GREEN rates and trends over time
  So that I can assess whether cycle reliability is improving

  Scenario: First-pass rate with no recorded cycles
    Given no TDD cycle records exist for playbook "playbook-1"
    When I request the first-pass rate for playbook "playbook-1"
    Then the result is 0.0

  Scenario: First-pass rate with all cycles succeeding on first attempt
    Given 4 TDD cycle records for playbook "playbook-1" with result "SUCCESS" and retry_count 0
    When I request the first-pass rate for playbook "playbook-1"
    Then the result is 1.0

  Scenario: First-pass rate counts only successes with zero retries
    Given 5 TDD cycle records for playbook "playbook-1":
      | result  | retry_count |
      | SUCCESS | 0           |
      | SUCCESS | 1           |
      | SUCCESS | 0           |
      | FAILURE | 0           |
      | SUCCESS | 2           |
    When I request the first-pass rate for playbook "playbook-1"
    Then the result is 0.4

  Scenario: First-pass rate filtered by playbook only counts matching cycles
    Given 3 TDD cycle records for playbook "playbook-1" with result "SUCCESS" and retry_count 0
    And 2 TDD cycle records for playbook "playbook-2" with result "FAILURE" and retry_count 1
    When I request the first-pass rate for playbook "playbook-1"
    Then the result is 1.0

  Scenario: Trend returns empty list when no cycles exist in the window
    Given no TDD cycle records exist for playbook "playbook-1"
    When I request the trend for playbook "playbook-1" over 10 periods of 7 days each
    Then the result is an empty list

  Scenario: Trend omits periods with no cycles and returns remaining periods oldest first
    Given TDD cycle records for playbook "playbook-1" with timestamps 3 days ago and 12 days ago, each with result "SUCCESS" and retry_count 0
    When I request the trend for playbook "playbook-1" over 3 periods of 7 days each
    Then the result contains 2 periods
    And the first period in the result covers the older time window
    And the last period in the result covers the more recent time window
    And each returned period has a first_pass_rate of 1.0

  Scenario: Trend computes per-period first-pass rate independently
    Given TDD cycle records for playbook "playbook-1" within the most recent 7-day period:
      | result  | retry_count |
      | SUCCESS | 0           |
      | SUCCESS | 1           |
      | FAILURE | 0           |
    When I request the trend for playbook "playbook-1" over 1 period of 7 days each
    Then the result contains 1 period
    And that period has total_cycles equal to 3
    And that period has first_pass_count equal to 1
    And that period has first_pass_rate of 0.3333333333333333