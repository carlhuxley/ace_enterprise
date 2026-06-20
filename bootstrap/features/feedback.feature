Feature: Human Feedback Collection and Score Blending

  Scenario: Submit valid human feedback
    Given a FeedbackCollector instance
    When I submit feedback with evaluationId "eval-001", rating 4, providerId "alice", providerRole "developer"
    Then the feedback is stored and returned
    And retrieving feedback for "eval-001" returns 1 item
    And the feedback has rating 4 and providerRole "developer"

  Scenario: Reject invalid rating outside 1-5 range
    Given a FeedbackCollector instance
    When I attempt to submit feedback with evaluationId "eval-002", rating 6, providerId "bob", providerRole "reviewer"
    Then a ValueError is raised with message containing "rating must be 1-5"

  Scenario: Blended score returns automated score when no feedback exists
    Given a FeedbackCollector instance
    When I compute blendedScore with automatedScore 75.0 and evaluationId "eval-003"
    Then the result is 75.0

  Scenario: Blended score incorporates human feedback
    Given a FeedbackCollector instance
    And I submit feedback with evaluationId "eval-004", rating 5, providerId "carol", providerRole "expert"
    When I compute blendedScore with automatedScore 50.0 and evaluationId "eval-004"
    Then the result is greater than 50.0 and less than or equal to 100.0

  Scenario: Aggregated rating returns mean of human ratings
    Given a FeedbackCollector instance
    And I submit feedback with evaluationId "eval-005", rating 3, providerId "dave", providerRole "developer"
    And I submit feedback with evaluationId "eval-005", rating 5, providerId "eve", providerRole "reviewer"
    When I call aggregatedRating for "eval-005"
    Then the result is 4.0

  Scenario: Aggregated rating returns None when no feedback exists
    Given a FeedbackCollector instance
    When I call aggregatedRating for "eval-999"
    Then the result is None

  Scenario: Detect drift when humans rate higher than automation
    Given a FeedbackCollector instance
    And I submit feedback with evaluationId "eval-006", rating 5, providerId "frank", providerRole "developer"
    When I call detectDrift with automatedScore 25.0 and evaluationId "eval-006"
    Then the result is positive

  Scenario: Detect drift returns zero when no feedback exists
    Given a FeedbackCollector instance
    When I call detectDrift with automatedScore 60.0 and evaluationId "eval-007"
    Then the result is 0.0

  Scenario: Drift report computes drift for multiple evaluations
    Given a FeedbackCollector instance
    And I submit feedback with evaluationId "eval-008", rating 2, providerId "grace", providerRole "developer"
    And I submit feedback with evaluationId "eval-009", rating 4, providerId "hank", providerRole "reviewer"
    When I call driftReport with automatedScores {"eval-008": 80.0, "eval-009": 50.0, "eval-010": 60.0}
    Then the result contains keys "eval-008" and "eval-009"
    And the result does not contain key "eval-010"

  Scenario: Get all feedback returns feedback across all evaluations
    Given a FeedbackCollector instance
    And I submit feedback with evaluationId "eval-011", rating 3, providerId "iris", providerRole "developer"
    And I submit feedback with evaluationId "eval-012", rating 5, providerId "jack", providerRole "expert"
    When I call getAllFeedback
    Then the result contains 2 items

  Scenario: Has feedback returns true when feedback exists
    Given a FeedbackCollector instance
    And I submit feedback with evaluationId "eval-013", rating 4, providerId "kate", providerRole "manager"
    When I call hasFeedback for "eval-013"
    Then the result is True

  Scenario: Has feedback returns false when no feedback exists
    Given a FeedbackCollector instance
    When I call hasFeedback for "eval-014"
    Then the result is False