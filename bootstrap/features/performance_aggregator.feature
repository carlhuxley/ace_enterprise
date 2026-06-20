Feature: Performance Aggregator
  Extracts performance metrics from audit trail without exposing content or identities

  Scenario: Get metrics for an agent with no audit events
    Given an audit store with no events
    And a performance aggregator using that store
    When I request metrics for agent "agent-001"
    Then the metrics show 0 total tasks
    And the metrics show 0 successful tasks
    And the metrics show 0 failed tasks
    And the success rate is 0.0
    And the reliability score is 0.0

  Scenario: Get metrics for an agent with successful and failed tasks
    Given an audit store with the following CYCLE_COMPLETED events for agent "agent-002":
      | success | elapsedSeconds | complexity | taskType | cost |
      | true    | 1.5             | 3          | coding    | 0.05 |
      | true    | 2.0             | 3          | coding    | 0.06 |
      | false   | 0.8             | 4          | math      | 0.03 |
      | true    | 1.2             | 2          | coding    | 0.04 |
    And a performance aggregator using that store
    When I request metrics for agent "agent-002"
    Then the metrics show 4 total tasks
    And the metrics show 3 successful tasks
    And the metrics show 1 failed tasks
    And the success rate is 0.75
    And the average latency is 1.375 seconds
    And the min latency is 0.8 seconds
    And the max latency is 2.0 seconds
    And the total cost is 0.18
    And the average cost per task is 0.045
    And the success rate for complexity 3 is 1.0
    And the success rate for complexity 4 is 0.0
    And the success rate for task type "coding" is 1.0
    And the success rate for task type "math" is 0.0

  Scenario: Reliability score increases with task volume
    Given an audit store with 3 successful CYCLE_COMPLETED events for agent "agent-low"
    And an audit store with 15 successful CYCLE_COMPLETED events for agent "agent-mid"
    And an audit store with 25 successful CYCLE_COMPLETED events for agent "agent-high"
    And a performance aggregator using that store
    When I request metrics for agent "agent-low"
    Then the reliability score is 0.5
    When I request metrics for agent "agent-mid"
    Then the reliability score is 0.8
    When I request metrics for agent "agent-high"
    Then the reliability score is 1.0

  Scenario: Check if agent can handle complexity level
    Given an audit store with the following CYCLE_COMPLETED events for agent "agent-003":
      | success | complexity |
      | true    | 2          |
      | true    | 2          |
      | true    | 2          |
      | false   | 3          |
      | false   | 3          |
      | true    | 3          |
    And a performance aggregator using that store
    When I request metrics for agent "agent-003"
    And I check if the agent can handle complexity 2 with minimum success rate 0.7
    Then the result is true
    When I check if the agent can handle complexity 3 with minimum success rate 0.7
    Then the result is false
    When I check if the agent can handle complexity 5 with minimum success rate 0.7
    Then the result is false

  Scenario: Get metrics for all agents
    Given an audit store with 2 successful CYCLE_COMPLETED events for agent "agent-A"
    And an audit store with 3 successful CYCLE_COMPLETED events for agent "agent-B"
    And a performance aggregator using that store
    When I request metrics for all agents
    Then the result contains metrics for agent "agent-A" with 2 total tasks
    And the result contains metrics for agent "agent-B" with 3 total tasks

  Scenario: Get best agent for task based on task type and complexity
    Given an audit store with the following CYCLE_COMPLETED events:
      | agentRef | success | taskType | complexity |
      | agent-X   | true    | coding    | 3          |
      | agent-X   | true    | coding    | 3          |
      | agent-X   | false   | math      | 3          |
      | agent-Y   | true    | math      | 3          |
      | agent-Y   | true    | math      | 3          |
      | agent-Y   | false   | coding    | 3          |
    And a performance aggregator using that store
    When I request the best agent for task type "coding" and complexity 3 with minimum success rate 0.7
    Then the result contains agent "agent-X" ranked higher than agent "agent-Y"
    When I request the best agent for task type "math" and complexity 3 with minimum success rate 0.7
    Then the result contains agent "agent-Y" ranked higher than agent "agent-X"

  Scenario: Build model profile with strengths and weaknesses
    Given an audit store with the following CYCLE_COMPLETED events for agent "agent-profile":
      | success | taskType | complexity |
      | true    | coding    | 2          |
      | true    | coding    | 2          |
      | true    | coding    | 3          |
      | false   | math      | 2          |
      | false   | math      | 3          |
      | true    | writing   | 2          |
    And a performance aggregator using that store
    When I request the model profile for agent "agent-profile"
    Then the profile shows "coding" as a strength
    And the profile shows "math" as a weakness
    And the optimal complexity is 2
    And the avoid complexity is 3

  Scenario: Variance adjusted reliability penalizes inconsistent quality
    Given an audit store with the following CYCLE_COMPLETED events for agent "agent-consistent":
      | success | qualityScore |
      | true    | 80.0          |
      | true    | 82.0          |
      | true    | 81.0          |
    And an audit store with the following CYCLE_COMPLETED events for agent "agent-variable":
      | success | qualityScore |
      | true    | 90.0          |
      | true    | 40.0          |
      | true    | 85.0          |
    And a performance aggregator using that store
    When I request metrics for agent "agent-consistent"
    Then the variance adjusted reliability is greater than 0.7
    When I request metrics for agent "agent-variable"
    Then the variance adjusted reliability is less than the reliability score

  Scenario: Latency quality correlation and tier breakdown
    Given an audit store with the following CYCLE_COMPLETED events for agent "agent-lq":
      | success | elapsedSeconds | qualityScore |
      | true    | 1.0             | 30.0          |
      | true    | 2.0             | 50.0          |
      | true    | 3.0             | 80.0          |
      | true    | 4.0             | 90.0          |
    And a performance aggregator using that store
    When I request the latency quality report for agent "agent-lq"
    Then the latency quality correlation is positive
    And the latency p50 by quality tier contains "low", "mid", and "high"
    And the sample count is 4

  Scenario: Find fastest model meeting quality threshold
    Given an audit store with the following CYCLE_COMPLETED events:
      | agentRef | success | elapsedSeconds |
      | agent-fast   | true    | 1.0             |
      | agent-fast   | true    | 1.2             |
      | agent-slow   | true    | 3.0             |
      | agent-slow   | true    | 3.5             |
      | agent-unreliable | true | 0.5            |
      | agent-unreliable | false | 0.6           |
      | agent-unreliable | false | 0.4           |
    And a performance aggregator using that store
    When I request the fastest model meeting quality threshold 0.7
    Then the result is "agent-fast"

  Scenario: Cache invalidation forces fresh metrics
    Given an audit store with 2 successful CYCLE_COMPLETED events for agent "agent-cache"
    And a performance aggregator using that store
    When I request metrics for agent "agent-cache"
    Then the metrics show 2 total tasks
    When 1 more successful CYCLE_COMPLETED event is added for agent "agent-cache"
    And I request metrics for agent "agent-cache"
    Then the metrics show 2 total tasks
    When I invalidate the cache
    And I request metrics for agent "agent-cache"
    Then the metrics show 3 total tasks

  Scenario: Bayesian estimate computed from success and failure counts
    Given an audit store with the following CYCLE_COMPLETED events for agent "agent-bayes":
      | success |
      | true    |
      | true    |
      | true    |
      | false   |
    And a performance aggregator using that store
    When I compute the bayesian estimate for agent "agent-bayes"
    Then the bayesian estimate has a mean between 0.5 and 0.9
    And the bayesian estimate has a credible interval

  Scenario: Regression alerts detect quality drops across versions
    Given an audit store with the following CYCLE_COMPLETED events for agent "agent-regress":
      | modelVersion | qualityScore |
      | v1.0          | 85.0          |
      | v1.0          | 87.0          |
      | v1.0          | 86.0          |
      | v2.0          | 60.0          |
      | v2.0          | 62.0          |
    And a performance aggregator using that store
    When I request regression alerts with regression threshold 0.15 and warning threshold 0.07
    Then the result contains at least one alert for agent "agent-regress"