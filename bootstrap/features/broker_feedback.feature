Feature: Human feedback collection, blended scoring, and drift detection

  As a caller of the evaluation pipeline
  I want to record human ratings and combine them with automated scores
  So that I can detect where automated scoring diverges from human judgement

  Scenario: Submitting a valid human rating
    Given no feedback has been submitted for evaluation "eval-101"
    When I submit a rating of 4 from provider "alice" with role "reviewer" for evaluation "eval-101"
    Then the submission succeeds
    And "eval-101" has feedback
    And retrieving feedback for "eval-101" returns exactly 1 entry with rating 4 from provider "alice"

  Scenario: Rejecting an out-of-range rating
    When I submit a rating of 6 from provider "bob" with role "developer" for evaluation "eval-102"
    Then a ValueError is raised

  Scenario: Blended score equals automated score when there is no feedback
    Given no feedback has been submitted for evaluation "eval-200"
    When I compute the blended score for automated score 70 on evaluation "eval-200"
    Then the blended score is 70

  Scenario: Blended score shifts toward a single fresh human rating
    Given a rating of 5 from provider "carol" with role "developer" was submitted for evaluation "eval-201" at the current reference time
    When I compute the blended score for automated score 70 on evaluation "eval-201" using that same reference time
    Then the blended score is greater than 70
    And the blended score is less than or equal to 100

  Scenario: Aggregated rating is the unweighted mean of submitted ratings
    Given a rating of 4 from provider "dave" with role "developer" was submitted for evaluation "eval-300"
    And a rating of 2 from provider "erin" with role "manager" was submitted for evaluation "eval-300"
    When I request the aggregated rating for evaluation "eval-300"
    Then the aggregated rating is 3.0

  Scenario: Aggregated rating is absent when there is no feedback
    Given no feedback has been submitted for evaluation "eval-301"
    When I request the aggregated rating for evaluation "eval-301"
    Then no aggregated rating is returned

  Scenario: Detecting positive drift when humans rate higher than automation
    Given a rating of 5 from provider "frank" with role "expert" was submitted for evaluation "eval-400" at the current reference time
    When I detect drift for automated score 70 on evaluation "eval-400" using that same reference time
    Then the drift value is greater than 0

  Scenario: Drift report only includes evaluations with both feedback and an automated score
    Given a rating of 5 from provider "gina" with role "developer" was submitted for evaluation "eval-500"
    And no feedback has been submitted for evaluation "eval-501"
    And automated scores are provided for evaluations "eval-500" and "eval-501"
    When I request a drift report for those automated scores
    Then the report contains an entry for "eval-500"
    And the report does not contain an entry for "eval-501"