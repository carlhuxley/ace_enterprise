Feature: Regression detector for tracking quality changes across model versions

  Scenario: Recording quality scores establishes a baseline
    Given no scores have been recorded for model "gpt-4" version "2024-01"
    When I record quality score 85.0 for model "gpt-4" version "2024-01"
    And I record quality score 88.0 for model "gpt-4" version "2024-01"
    Then the baseline for model "gpt-4" version "2024-01" has mean score 86.5
    And the baseline has sample count 2

  Scenario: No baseline exists for an unrecorded version
    Given no scores have been recorded for model "gpt-4" version "9999-01"
    When I request the baseline for model "gpt-4" version "9999-01"
    Then no baseline is returned

  Scenario: Version history is returned in first-seen order
    Given I record a quality score for model "gpt-4" version "2024-01"
    And I record a quality score for model "gpt-4" version "2024-02"
    And I record a quality score for model "gpt-4" version "2024-03"
    When I request the version history for model "gpt-4"
    Then the version history is ["2024-01", "2024-02", "2024-03"]

  Scenario: Known models list reflects all recorded model IDs
    Given I record a quality score for model "gpt-4" version "2024-01"
    And I record a quality score for model "claude-3" version "2024-01"
    When I request the list of known models
    Then the list contains "gpt-4" and "claude-3"

  Scenario: A large quality drop is flagged as a regression
    Given model "gpt-4" version "2024-01" has recorded scores [85.0, 87.0, 86.0]
    And model "gpt-4" version "2024-02" has recorded scores [65.0, 66.0, 64.0]
    When I detect a regression between baseline version "2024-01" and current version "2024-02" for model "gpt-4"
    Then a regression alert is returned with severity "REGRESSION_DETECTED"
    And the alert reports baseline mean 86.0 and current mean 65.0

  Scenario: A moderate quality drop is flagged as a warning
    Given model "gpt-4" version "2024-01" has recorded scores [100.0, 100.0]
    And model "gpt-4" version "2024-02" has recorded scores [91.0, 91.0]
    When I detect a regression between baseline version "2024-01" and current version "2024-02" for model "gpt-4"
    Then a regression alert is returned with severity "WARNING"

  Scenario: A small quality drop produces no alert
    Given model "gpt-4" version "2024-01" has recorded scores [100.0, 100.0]
    And model "gpt-4" version "2024-02" has recorded scores [98.0, 98.0]
    When I detect a regression between baseline version "2024-01" and current version "2024-02" for model "gpt-4"
    Then no regression alert is returned

  Scenario: CUSUM detects a sustained downward shift in a raw score sequence
    Given a quality score sequence [90.0, 90.0, 90.0, 40.0, 40.0, 40.0, 40.0, 40.0]
    And an expected baseline mean of 90.0
    When I run CUSUM change-point detection on the sequence
    Then a change-point index is returned within the sequence

  Scenario: Generating a report summarizes baselines and alerts across versions
    Given model "gpt-4" version "2024-01" has recorded scores [85.0, 87.0, 86.0]
    And model "gpt-4" version "2024-02" has recorded scores [65.0, 66.0, 64.0]
    When I generate a report for model "gpt-4"
    Then the report includes versions ["2024-01", "2024-02"]
    And the report includes a baseline entry for version "2024-01" with mean 86.0
    And the report includes an alert from "2024-01" to "2024-02" with severity "REGRESSION_DETECTED"