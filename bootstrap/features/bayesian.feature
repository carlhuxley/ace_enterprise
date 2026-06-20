Feature: Bayesian success-rate estimation using Beta-Binomial model

  Scenario: Estimate success rate with no observations and uniform prior
    When estimate_success_rate is called with successes=0 and failures=0
    Then the mean is 0.5
    And the alpha_posterior is 1.0
    And the beta_posterior is 1.0
    And the confidence_level is 0.95
    And the ci_width is greater than 0.30
    And is_insufficient_data is True

  Scenario: Estimate success rate with balanced observations
    When estimate_success_rate is called with successes=50 and failures=50
    Then the mean is 0.5
    And the alpha_posterior is 51.0
    And the beta_posterior is 51.0
    And the ci_width is less than 0.30
    And is_insufficient_data is False

  Scenario: Estimate success rate with high success rate and sufficient data
    When estimate_success_rate is called with successes=90 and failures=10
    Then the mean is approximately 0.89
    And the alpha_posterior is 91.0
    And the beta_posterior is 11.0
    And the ci_lower is less than the mean
    And the ci_upper is greater than the mean
    And the ci_width equals ci_upper minus ci_lower
    And is_insufficient_data is False

  Scenario: Estimate success rate with sparse data
    When estimate_success_rate is called with successes=2 and failures=1
    Then the alpha_posterior is 3.0
    And the beta_posterior is 2.0
    And the ci_width is greater than 0.30
    And is_insufficient_data is True

  Scenario: Estimate success rate with custom prior
    When estimate_success_rate is called with successes=10, failures=5, prior_alpha=5.0, and prior_beta=5.0
    Then the alpha_posterior is 15.0
    And the beta_posterior is 10.0
    And the mean is 0.6
    And the confidence_level is 0.95

  Scenario: Estimate success rate with custom confidence level
    When estimate_success_rate is called with successes=50, failures=50, and confidence_level=0.90
    Then the confidence_level is 0.90
    And the ci_width is less than the ci_width for confidence_level=0.95 with same data

  Scenario: Estimate success rate with only successes
    When estimate_success_rate is called with successes=20 and failures=0
    Then the alpha_posterior is 21.0
    And the beta_posterior is 1.0
    And the mean is approximately 0.95
    And the ci_lower is greater than 0.0
    And the ci_upper is less than 1.0

  Scenario: Estimate success rate with only failures
    When estimate_success_rate is called with successes=0 and failures=20
    Then the alpha_posterior is 1.0
    And the beta_posterior is 21.0
    And the mean is approximately 0.05
    And the ci_lower is greater than 0.0
    And the ci_upper is less than 1.0