Feature: Feedback REST API
  Feedback submission and querying endpoints for human evaluation feedback

  Scenario: Submit feedback with all fields
    Given a feedback collector is available
    When a POST request is made to "/" with body:
      | evaluationId | rating | providerId | providerRole | comment          |
      | eval-123      | 4      | user-42     | developer     | Looks good       |
    Then the response status code is 201
    And the response contains evaluationId "eval-123"
    And the response contains rating 4
    And the response contains providerId "user-42"
    And the response contains providerRole "developer"
    And the response contains comment "Looks good"
    And the response contains a timestamp

  Scenario: Submit feedback without optional comment
    Given a feedback collector is available
    When a POST request is made to "/" with body:
      | evaluationId | rating | providerId | providerRole |
      | eval-456      | 5      | user-99     | reviewer      |
    Then the response status code is 201
    And the response contains evaluationId "eval-456"
    And the response contains rating 5
    And the response contains comment null

  Scenario: Submit feedback with invalid rating below minimum
    Given a feedback collector is available
    When a POST request is made to "/" with body:
      | evaluationId | rating | providerId | providerRole |
      | eval-789      | 0      | user-10     | expert        |
    Then the response status code is 422

  Scenario: Submit feedback with invalid rating above maximum
    Given a feedback collector is available
    When a POST request is made to "/" with body:
      | evaluationId | rating | providerId | providerRole |
      | eval-789      | 6      | user-10     | expert        |
    Then the response status code is 422

  Scenario: Submit feedback with blank providerRole
    Given a feedback collector is available
    When a POST request is made to "/" with body:
      | evaluationId | rating | providerId | providerRole |
      | eval-111      | 3      | user-20     |               |
    Then the response status code is 422

  Scenario: Get all feedback for an evaluation
    Given a feedback collector is available
    When a GET request is made to "/eval-555"
    Then the response status code is 200
    And the response contains evaluationId "eval-555"
    And the response contains a feedbacks list
    And the response contains an aggregatedRating field

  Scenario: Get drift with valid automated score
    Given a feedback collector is available
    When a GET request is made to "/eval-777/drift" with query parameter automatedScore 75.5
    Then the response status code is 200
    And the response contains evaluationId "eval-777"
    And the response contains automatedScore 75.5
    And the response contains a drift value
    And the response contains a blendedScore value

  Scenario: Get drift with automated score below valid range
    Given a feedback collector is available
    When a GET request is made to "/eval-888/drift" with query parameter automatedScore -5.0
    Then the response status code is 422
    And the response detail contains "automatedScore must be in [0, 100]"

  Scenario: Get drift with automated score above valid range
    Given a feedback collector is available
    When a GET request is made to "/eval-999/drift" with query parameter automatedScore 150.0
    Then the response status code is 422
    And the response detail contains "automatedScore must be in [0, 100]"

  Scenario: Get drift with default automated score
    Given a feedback collector is available
    When a GET request is made to "/eval-000/drift" without query parameters
    Then the response status code is 200
    And the response contains automatedScore 0.0