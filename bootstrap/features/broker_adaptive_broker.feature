Feature: Adaptive task routing based on learned agent performance

  As a caller of AdaptiveBroker
  I want tasks routed to the agent most likely to succeed
  So that I get a confident recommendation along with all alternatives considered

  Scenario: No performance history falls back to the default agent
    Given an AdaptiveBroker with no historical agent performance data
    When I route a task with type "code_review" and complexity 3
    Then the selected agent is "default-agent"
    And the confidence is 0.0
    And the verdict is "ASK_FIRST"
    And the result is marked as a fallback
    And the candidates list is empty

  Scenario: No performance history uses a configured fallback agent
    Given an AdaptiveBroker with no historical agent performance data
    And the fallback agent has been set to "claude-sonnet-5"
    When I route a task with type "bug_fix" and complexity 2
    Then the selected agent is "claude-sonnet-5"
    And the result is marked as a fallback

  Scenario: High-performing agent is selected and returns an APPLY verdict
    Given an AdaptiveBroker with performance history showing "agent-a" has a strong track record on "refactor" tasks
    When I route a task with type "refactor" and complexity 4
    Then the selected agent is "agent-a"
    And the confidence is at least 0.70
    And the verdict is "APPLY"
    And the result is not marked as a fallback

  Scenario: Moderate confidence produces an ASK_FIRST verdict
    Given an AdaptiveBroker with performance history showing agents have mixed, moderate success on "documentation" tasks
    When I route a task with type "documentation" and complexity 1
    Then the confidence is between 0.35 and 0.70
    And the verdict is "ASK_FIRST"

  Scenario: Sparse or poor performance history produces a SKIP verdict
    Given an AdaptiveBroker with performance history showing all agents perform poorly on "security_audit" tasks
    When I route a task with type "security_audit" and complexity 5
    Then the confidence is below 0.35
    And the verdict is "SKIP"

  Scenario: Budget routing mode filters out agents that exceed the cost cap
    Given an AdaptiveBroker configured with routing mode "BUDGET" and a maximum cost per task of 0.05
    And performance history where "agent-expensive" costs 0.20 per task and "agent-cheap" costs 0.02 per task
    When I route a task with type "summarization" and complexity 2
    Then the selected agent is "agent-cheap"

  Scenario: Budget routing mode falls back to the cheapest agent when all exceed the cost cap
    Given an AdaptiveBroker configured with routing mode "BUDGET" and a maximum cost per task of 0.01
    And performance history where every agent costs more than 0.01 per task
    When I route a task with type "summarization" and complexity 2
    Then the selected agent is the agent with the lowest average cost per task
    And the confidence is 0.0

  Scenario: Latency cap excludes agents that are too slow, keeping agents with no latency history
    Given an AdaptiveBroker configured with a maximum average latency of 2.0 seconds
    And performance history where "agent-slow" has an average latency of 5.0 seconds and "agent-new" has no recorded latency
    When I route a task with type "analysis" and complexity 3
    Then the selected agent is not "agent-slow"