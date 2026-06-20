Feature: Regression Detector for Model Quality Tracking

  Scenario: Recording quality scores for a single model version
    Given a regression detector with default thresholds
    When I record quality score 85.0 for model "gpt-4" version "2024-01"
    And I record quality score 88.0 for model "gpt-4" version "2024-01"
    And I record quality score 90.0 for model "gpt-4" version "2024-01"
    Then the baseline for model "gpt-4" version "2024-01" has mean score 87.666667
    And the baseline for model "gpt-4" version "2024-01" has sample count 3

  Scenario: Retrieving version history in first-seen order
    Given a regression detector with default thresholds
    When I record quality score 85.0 for model "gpt-4" version "2024-01"
    And I record quality score 88.0 for model "gpt-4" version "2024-02"
    And I record quality score 90.0 for model "gpt-4" version "2024-01"
    And I record quality score 92.0 for model "gpt-4" version "2024-03"
    Then the version history for model "gpt-4" is ["2024-01", "2024-02", "2024-03"]

  Scenario: No regression detected when quality remains stable
    Given a regression detector with default thresholds
    When I record quality score 85.0 for model "gpt-4" version "2024-01"
    And I record quality score 88.0 for model "gpt-4" version "2024-01"
    And I record quality score 86.0 for model "gpt-4" version "2024-02"
    And I record quality score 87.0 for model "gpt-4" version "2024-02"
    Then detecting regression between "2024-01" and "2024-02" for model "gpt-4" returns None

  Scenario: Warning alert when quality drops by 10 percent
    Given a regression detector with default thresholds
    When I record quality score 100.0 for model "gpt-4" version "2024-01"
    And I record quality score 100.0 for model "gpt-4" version "2024-01"
    And I record quality score 90.0 for model "gpt-4" version "2024-02"
    And I record quality score 90.0 for model "gpt-4" version "2024-02"
    Then detecting regression between "2024-01" and "2024-02" for model "gpt-4" returns an alert with severity "WARNING"
    And the alert has baseline mean 100.0
    And the alert has current mean 90.0
    And the alert has drop fraction 0.1

  Scenario: Regression detected when quality drops by 20 percent
    Given a regression detector with default thresholds
    When I record quality score 100.0 for model "gpt-4" version "2024-01"
    And I record quality score 100.0 for model "gpt-4" version "2024-01"
    And I record quality score 80.0 for model "gpt-4" version "2024-02"
    And I record quality score 80.0 for model "gpt-4" version "2024-02"
    Then detecting regression between "2024-01" and "2024-02" for model "gpt-4" returns an alert with severity "REGRESSION_DETECTED"
    And the alert has drop fraction 0.2

  Scenario: Check all detects regressions across multiple consecutive versions
    Given a regression detector with default thresholds
    When I record quality score 100.0 for model "gpt-4" version "v1"
    And I record quality score 100.0 for model "gpt-4" version "v1"
    And I record quality score 90.0 for model "gpt-4" version "v2"
    And I record quality score 90.0 for model "gpt-4" version "v2"
    And I record quality score 75.0 for model "gpt-4" version "v3"
    And I record quality score 75.0 for model "gpt-4" version "v3"
    Then checking all regressions returns 2 alerts
    And alert 0 has baseline version "v1" and current version "v2" with severity "WARNING"
    And alert 1 has baseline version "v2" and current version "v3" with severity "REGRESSION_DETECTED"

  Scenario: Window limits current version samples used for comparison
    Given a regression detector with window size 2
    When I record quality score 100.0 for model "gpt-4" version "2024-01"
    And I record quality score 100.0 for model "gpt-4" version "2024-01"
    And I record quality score 80.0 for model "gpt-4" version "2024-02"
    And I record quality score 80.0 for model "gpt-4" version "2024-02"
    And I record quality score 100.0 for model "gpt-4" version "2024-02"
    And I record quality score 100.0 for model "gpt-4" version "2024-02"
    Then detecting regression between "2024-01" and "2024-02" for model "gpt-4" returns an alert with severity "REGRESSION_DETECTED"
    And the alert has sample count 2
    And the alert has current mean 80.0

  Scenario: CUSUM detects change-point in quality score sequence
    Given a regression detector with default thresholds
    When I apply CUSUM detection to scores [100.0, 100.0, 100.0, 80.0, 80.0, 80.0] with baseline mean 100.0 and kFactor 0.05 and threshold 5.0
    Then CUSUM returns change-point index 3

  Scenario: Generate report summarizes model versions and alerts
    Given a regression detector with default thresholds
    When I record quality score 100.0 for model "gpt-4" version "v1"
    And I record quality score 100.0 for model "gpt-4" version "v1"
    And I record quality score 80.0 for model "gpt-4" version "v2"
    And I record quality score 80.0 for model "gpt-4" version "v2"
    Then the report for model "gpt-4" contains versions ["v1", "v2"]
    And the report contains baseline for "v1" with mean 100.0 and sample count 2
    And the report contains baseline for "v2" with mean 80.0 and sample count 2
    And the report contains 1 alert with baseline version "v1" and current version "v2"