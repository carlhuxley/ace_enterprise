Feature: Broker Advisor Recommends Agents by Capability Fit

  Scenario: Recommend agents when no agents are registered
    Given a capability registry with no agents
    And an advisor using that registry
    And task requirements for task "task-1" requiring capability "python" at proficiency 0.8
    When I request recommendations for those requirements
    Then I receive an empty list of recommendations

  Scenario: Recommend single agent that fully meets requirements
    Given a capability registry with agent "agent-ref-1" having capability "python" at proficiency 0.9
    And an advisor using that registry
    And task requirements for task "task-1" requiring capability "python" at proficiency 0.8
    When I request recommendations for those requirements
    Then I receive 1 recommendation
    And the recommendation has agentRef "agent-ref-1"
    And the recommendation has meetsRequirements True
    And the recommendation has capabilityMatch greater than 0.0

  Scenario: Exclude agents that do not meet requirements by default
    Given a capability registry with agent "agent-ref-1" having capability "python" at proficiency 0.5
    And an advisor using that registry
    And task requirements for task "task-1" requiring capability "python" at proficiency 0.8
    When I request recommendations for those requirements
    Then I receive an empty list of recommendations

  Scenario: Include partial matches when requested
    Given a capability registry with agent "agent-ref-1" having capability "python" at proficiency 0.5
    And an advisor using that registry
    And task requirements for task "task-1" requiring capability "python" at proficiency 0.8
    When I request recommendations with includePartial True
    Then I receive 1 recommendation
    And the recommendation has agentRef "agent-ref-1"
    And the recommendation has meetsRequirements False

  Scenario: Rank multiple agents by capability match score
    Given a capability registry with agent "agent-ref-1" having capability "python" at proficiency 0.9
    And the registry also has agent "agent-ref-2" having capability "python" at proficiency 1.0
    And an advisor using that registry
    And task requirements for task "task-1" requiring capability "python" at proficiency 0.8
    When I request recommendations for those requirements
    Then I receive 2 recommendations
    And the first recommendation has agentRef "agent-ref-2"
    And the second recommendation has agentRef "agent-ref-1"

  Scenario: Include historical success rates in recommendations
    Given a capability registry with agent "agent-ref-1" having capability "python" at proficiency 0.9
    And an advisor using that registry with success rate 0.85 for capability "python"
    And task requirements for task "task-1" requiring capability "python" at proficiency 0.8
    When I request recommendations for those requirements
    Then I receive 1 recommendation
    And the recommendation has successRate 0.85

  Scenario: Calculate average success rate across multiple required capabilities
    Given a capability registry with agent "agent-ref-1" having capabilities "python" at 0.9 and "testing" at 0.8
    And an advisor using that registry with success rate 0.9 for "python" and 0.8 for "testing"
    And task requirements for task "task-1" requiring capabilities "python" at 0.7 and "testing" at 0.7
    When I request recommendations for those requirements
    Then I receive 1 recommendation
    And the recommendation has successRate 0.85

  Scenario: Get summary when no agents match
    Given a capability registry with no agents
    And an advisor using that registry
    And task requirements for task "task-1" requiring capability "python" at proficiency 0.8
    When I request a summary for those requirements
    Then the summary contains "No agents match requirements for: python"

  Scenario: Get summary with match count and best score
    Given a capability registry with agent "agent-ref-1" having capability "python" at proficiency 0.9
    And the registry also has agent "agent-ref-2" having capability "python" at proficiency 0.85
    And an advisor using that registry
    And task requirements for task "task-1" requiring capability "python" at proficiency 0.8
    When I request a summary for those requirements
    Then the summary contains "2 agents match requirements for python"
    And the summary contains "Best match score:"

  Scenario: Get summary includes historical success rate when available
    Given a capability registry with agent "agent-ref-1" having capability "python" at proficiency 0.9
    And an advisor using that registry with success rate 0.93 for capability "python"
    And task requirements for task "task-1" requiring capability "python" at proficiency 0.8
    When I request a summary for those requirements
    Then the summary contains "93% historical success rate"