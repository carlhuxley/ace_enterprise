Feature: Adaptive Broker
  Routes tasks to the best available agent based on performance history and routing mode

  Scenario: Route with no performance history uses fallback agent
    Given an AdaptiveBroker with fallback agent "default-agent" and no performance data
    When route_task is called
    Then the selected agent is "default-agent"
    And is_fallback is true

  Scenario: Route with high-confidence history returns APPLY verdict
    Given an AdaptiveBroker with agent "agent-a" having 100 tasks at 0.95 success rate
    And apply_threshold is 0.70
    When route_task is called
    Then the selected agent is "agent-a"
    And the verdict is "APPLY"

  Scenario: Route with low confidence returns SKIP verdict
    Given an AdaptiveBroker with agent "agent-b" having 10 tasks at 0.20 success rate
    And ask_threshold is 0.35
    When route_task is called
    Then the verdict is "SKIP"
    And the confidence is below 0.35

  Scenario: Route in BUDGET mode excludes agents above cost cap
    Given an AdaptiveBroker in BUDGET mode with max_cost_per_task 0.50
    And agent "expensive" has avg_cost_per_task 0.80 and success rate 0.95
    And agent "cheap" has avg_cost_per_task 0.30 and success rate 0.85
    When route_task is called
    Then the selected agent is "cheap"

  Scenario: Route in PARETO mode excludes dominated agents
    Given an AdaptiveBroker in PARETO mode
    And agent "pareto-a" has success rate 0.90 and avg_cost 0.30
    And agent "pareto-b" has success rate 0.95 and avg_cost 0.50
    And agent "dominated" has success rate 0.85 and avg_cost 0.60
    When route_task is called
    Then "dominated" is not among the candidates
