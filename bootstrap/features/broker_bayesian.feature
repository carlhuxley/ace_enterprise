Feature: Bayesian success-rate estimation

  Scenario: Uniform prior with no observations yields maximum uncertainty
    Given 0 successes and 0 failures
    When the success rate is estimated with default priors
    Then the posterior mean is 0.5
    And the estimate is flagged as insufficient data

  Scenario: Balanced observations produce a mean near 0.5
    Given 5 successes and 5 failures
    When the success rate is estimated with default priors
    Then the posterior mean is 0.5
    And the credible interval lower bound is less than the posterior mean
    And the credible interval upper bound is greater than the posterior mean

  Scenario: Large sample size produces a narrow credible interval
    Given 950 successes and 50 failures
    When the success rate is estimated with default priors
    Then the posterior mean is approximately 0.951
    And the estimate is not flagged as insufficient data

  Scenario: Small sample size produces a wide credible interval
    Given 2 successes and 1 failure
    When the success rate is estimated with default priors
    Then the estimate is flagged as insufficient data

  Scenario: Custom prior shifts the posterior mean toward the prior belief
    Given 1 success and 1 failure
    And a prior alpha of 10 and prior beta of 1
    When the success rate is estimated with these priors
    Then the posterior mean is approximately 0.917

  Scenario: All observed outcomes are successes
    Given 100 successes and 0 failures
    When the success rate is estimated with default priors
    Then the posterior mean is approximately 0.99
    And the credible interval upper bound is less than or equal to 1.0

  Scenario: All observed outcomes are failures
    Given 0 successes and 100 failures
    When the success rate is estimated with default priors
    Then the posterior mean is approximately 0.0098
    And the credible interval lower bound is greater than or equal to 0.0

  Scenario: Narrower confidence level produces a narrower credible interval than the default
    Given 20 successes and 20 failures
    When the success rate is estimated with a confidence level of 0.80
    And the success rate is estimated with a confidence level of 0.95
    Then the credible interval width at confidence level 0.80 is smaller than at confidence level 0.95