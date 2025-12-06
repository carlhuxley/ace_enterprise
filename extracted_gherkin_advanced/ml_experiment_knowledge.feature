Feature: ML Experiment Decision Tracking
  Captures a decision made during ML experimentation.

  Scenario: To dict
    Given an ML experiment with a decision to record
    When I to dict
    Then the decision should be properly recorded

  Scenario: From dict
    Given an ML experiment with a decision to record
    When I from dict
    Then the decision should be properly recorded

