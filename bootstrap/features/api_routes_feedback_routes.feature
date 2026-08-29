Feature: Human feedback submission and retrieval API

  Scenario: Submit valid feedback for an evaluation
    Given an evaluation with id "eval-123"
    When a client submits feedback with rating 4, provider_id "user-42", provider_role "reviewer", and comment "Looks solid"
    Then the response status is 201
    And the response contains evaluation_id "eval-123", rating 4, provider_id "user-42", provider_role "reviewer", and comment "Looks solid"
    And the response includes a timestamp

  Scenario: Reject feedback with a rating outside the allowed range
    Given an evaluation with id "eval-123"
    When a client submits feedback with rating 7, provider_id "user-42", and provider_role "reviewer"
    Then the request is rejected with a validation error

  Scenario: Reject feedback with a blank provider role
    Given an evaluation with id "eval-123"
    When a client submits feedback with rating 3, provider_id "user-42", and provider_role "   "
    Then the request is rejected with a validation error

  Scenario: Retrieve all feedback and aggregated rating for an evaluation
    Given evaluation "eval-123" has received feedback with ratings 4 and 2 from two different providers
    When a client requests feedback for evaluation "eval-123"
    Then the response lists 2 feedback entries
    And the response reports an aggregated_rating of 3.0

  Scenario: Retrieve feedback for an evaluation with no submissions yet
    Given evaluation "eval-999" has received no feedback
    When a client requests feedback for evaluation "eval-999"
    Then the response lists 0 feedback entries
    And the response reports an aggregated_rating of null

  Scenario: Calculate drift between automated and human scores
    Given evaluation "eval-123" has an aggregated human rating
    When a client requests drift for evaluation "eval-123" with automated_score 80.0
    Then the response contains evaluation_id "eval-123", automated_score 80.0, a drift value, and a blended_score value

  Scenario: Reject drift request with an out-of-range automated score
    Given evaluation "eval-123" exists
    When a client requests drift for evaluation "eval-123" with automated_score 150.0
    Then the response status is 422
    And the response contains the detail "automated_score must be in [0, 100]"