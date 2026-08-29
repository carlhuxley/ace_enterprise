Feature: Success rate calculation across experiments, types, versions, and time

  Scenario: Overall success rate with a mix of results
    Given the experiment logger has 4 records with results "SUCCESS", "SUCCESS", "FAILURE", "SUCCESS"
    When I request the overall success rate
    Then the result is 0.75

  Scenario: Overall success rate with no matching records
    Given the experiment logger has no records
    When I request the overall success rate
    Then the result is 0.0

  Scenario: Overall success rate filtered by experiment type
    Given the experiment logger has 2 records of type "canary" with results "SUCCESS", "FAILURE"
    And the experiment logger has 3 records of type "rollback" with results "SUCCESS", "SUCCESS", "SUCCESS"
    When I request the overall success rate for experiment type "rollback"
    Then the result is 1.0

  Scenario: Success rate broken down by experiment type
    Given the experiment logger has 2 records of type "canary" with results "SUCCESS", "FAILURE"
    And the experiment logger has 2 records of type "rollback" with results "SUCCESS", "SUCCESS"
    When I request the success rate by type
    Then the result includes "canary" mapped to 0.5
    And the result includes "rollback" mapped to 1.0

  Scenario: Success rate broken down by playbook version, newest first
    Given the experiment logger has 2 records with playbook version "v1.0.0" and results "SUCCESS", "FAILURE"
    And the experiment logger has 1 record with playbook version "v2.0.0" and result "SUCCESS"
    When I request the success rate by playbook version
    Then the result is a list starting with version "v2.0.0" having total 1, success_count 1, and success_rate 1.0
    And the result then includes version "v1.0.0" having total 2, success_count 1, and success_rate 0.5

  Scenario: Trend over weekly periods omits periods with no experiments
    Given the experiment logger has 1 record timestamped 3 days ago with result "SUCCESS"
    And the experiment logger has 2 records timestamped 20 days ago with results "SUCCESS", "FAILURE"
    And there are no records timestamped between 8 and 14 days ago
    When I request the trend for 3 periods of 7 days each
    Then the result contains 2 periods ordered oldest first
    And the oldest period has total 2 and success_rate 0.5
    And the most recent period has total 1 and success_rate 1.0

  Scenario: Trend with no experiments in the lookback window returns an empty list
    Given the experiment logger has no records within the last 70 days
    When I request the trend for 10 periods of 7 days each
    Then the result is an empty list