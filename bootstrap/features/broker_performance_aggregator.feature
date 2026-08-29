Feature: Performance Aggregator - Agent Performance Metrics
  As a caller of the PerformanceAggregator
  I want to derive performance, reliability, and profile information for agents
  So that I can select agents for tasks without ever accessing prompt or output content

  Scenario: Aggregating success and failure counts for a single agent
    Given an agent "agent-42" has 7 completed cycle events in the audit trail
    And 5 of those events have "success" set to true and 2 have "success" set to false
    When I request performance metrics for "agent-42"
    Then the returned metrics report 7 total tasks
    And the returned metrics report 5 successful tasks and 2 failed tasks
    And the success rate is approximately 0.714

  Scenario: Reliability score is discounted for agents with few recorded tasks
    Given an agent "agent-low-volume" has 3 completed cycle events, all successful
    When I request performance metrics for "agent-low-volume"
    Then the success rate is 1.0
    But the reliability score is 0.5
    Because agents with fewer than 5 recorded tasks have their reliability score halved

  Scenario: Selecting the best agent for a task type and complexity level
    Given agent "agent-a" has a success rate of 0.9 for task type "coding" at complexity 3
    And agent "agent-b" has a success rate of 0.4 for task type "coding" at complexity 3
    When I request the best agents for task type "coding" at complexity 3 with a minimum success rate of 0.7
    Then "agent-a" appears in the ranked results with a higher confidence score than "agent-b"
    And agents scoring below half of the minimum success rate are excluded from the results

  Scenario: Building a model profile identifies strengths and weaknesses by task type
    Given agent "agent-42" has success rates of 0.95 for "coding", 0.80 for "math", and 0.50 for "writing"
    When I request the model profile for "agent-42"
    Then "coding" is listed as a strength
    And "writing" is listed as a weakness
    And "math" is listed in neither strengths nor weaknesses

  Scenario: Finding the fastest agent that meets a minimum quality bar
    Given agent "agent-fast" has a reliability score of 0.85 and an average latency of 2.0 seconds
    And agent "agent-slow" has a reliability score of 0.90 and an average latency of 8.0 seconds
    And agent "agent-unreliable" has a reliability score of 0.40 and an average latency of 1.0 seconds
    When I request the fastest agent meeting a minimum quality of 0.7
    Then "agent-fast" is returned
    And "agent-unreliable" is not considered because its reliability score is below the minimum

  Scenario: Blending automated score with human feedback
    Given agent "agent-42" has a reliability score of 0.8
    And evaluation "eval-1" has human feedback recorded for it
    And blending the automated score with the feedback for "eval-1" produces 75.0
    When I request the feedback-adjusted score for "agent-42" using evaluation ids ["eval-1"]
    Then the returned score is 75.0

  Scenario: Feedback-adjusted score falls back to the automated score when no feedback exists
    Given agent "agent-42" has a reliability score of 0.8
    And none of the supplied evaluation ids have recorded feedback
    When I request the feedback-adjusted score for "agent-42" using evaluation ids ["eval-2", "eval-3"]
    Then the returned score equals the automated reliability score expressed as a percentage

  Scenario: Metrics are cached until explicitly invalidated
    Given agent "agent-42" has previously had its metrics computed and cached
    And a new completed cycle event for "agent-42" has since been added to the audit trail
    When I request performance metrics for "agent-42" again without invalidating the cache
    Then the returned metrics do not include the new event
    When I invalidate the cache and request performance metrics for "agent-42" again
    Then the returned metrics include the new event