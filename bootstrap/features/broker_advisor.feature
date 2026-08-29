Feature: BrokerAdvisor capability-based agent recommendation
  As a system selecting agents for a task
  I want recommendations based purely on capability fit
  So that agent identity, cost, and business priorities remain hidden from the decision process

  Background:
    Given a capability registry containing agent "agent-1" with capabilities:
      | capability | proficiency |
      | python     | 0.9         |
      | testing    | 0.8         |
    And the registry also contains agent "agent-2" with capabilities:
      | capability | proficiency |
      | python     | 0.5         |

  Scenario: Recommend only agents that fully meet requirements by default
    Given task requirements "task-1" needing capabilities:
      | capability | min_proficiency |
      | python     | 0.7             |
      | testing    | 0.7             |
    When I request recommendations for "task-1"
    Then the recommendation list contains exactly agent "agent-1"
    And the recommendation for "agent-1" has meets_requirements equal to true

  Scenario: Include partially matching agents when requested
    Given task requirements "task-2" needing capabilities:
      | capability | min_proficiency |
      | python     | 0.7             |
    When I request recommendations for "task-2" including partial matches
    Then the recommendation list contains agent "agent-1" and agent "agent-2"
    And the recommendation for "agent-2" has meets_requirements equal to false
    And the recommendation for "agent-2" has a lower capability_match than "agent-1"

  Scenario: Recommendations are ranked by capability match in descending order
    Given task requirements "task-3" needing capabilities:
      | capability | min_proficiency |
      | python     | 0.4             |
    When I request recommendations for "task-3" including partial matches
    Then the first recommendation in the list has the highest capability_match value

  Scenario: No recommendations when no agent meets the requirements
    Given task requirements "task-4" needing capabilities:
      | capability | min_proficiency |
      | rust       | 0.5             |
    When I request recommendations for "task-4"
    Then the recommendation list is empty

  Scenario: Recommendations never reveal agent identity or cost information
    Given task requirements "task-5" needing capabilities:
      | capability | min_proficiency |
      | python     | 0.7             |
    When I request recommendations for "task-5"
    Then each recommendation exposes only an opaque agent reference, a capability_match score, a meets_requirements flag, and an optional success_rate

  Scenario: Summary reports match counts and best score without identities
    Given task requirements "task-6" needing capabilities:
      | capability | min_proficiency |
      | python     | 0.7             |
      | testing    | 0.7             |
    When I request a summary for "task-6"
    Then the summary text mentions the number of matching agents
    And the summary text mentions the best match score as a percentage
    And the summary text does not contain any agent identity or cost information

  Scenario: Summary reflects historical success rate when available
    Given a capability registry containing agent "agent-3" with capabilities:
      | capability | proficiency |
      | python     | 0.9         |
    And the advisor was configured with a historical success rate of 0.93 for capability "python"
    And task requirements "task-7" needing capabilities:
      | capability | min_proficiency |
      | python     | 0.7             |
    When I request a summary for "task-7"
    Then the summary text includes "93% historical success rate"

  Scenario: Summary explains when no agents match
    Given task requirements "task-8" needing capabilities:
      | capability | min_proficiency |
      | rust       | 0.5             |
    When I request a summary for "task-8"
    Then the summary text states that no agents match requirements for "rust"