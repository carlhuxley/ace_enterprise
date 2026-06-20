Feature: Audit Dashboard Analysis

  Scenario: Calculate agent performance from audit events
    Given audit events containing completed cycles for agent "agent-001"
      | eventType      | actorId   | success |
      | CYCLE_COMPLETED | agent-001  | true    |
      | CYCLE_COMPLETED | agent-001  | true    |
      | CYCLE_COMPLETED | agent-001  | false   |
    When I get agent performance
    Then agent "agent-001" has total tasks 3
    And agent "agent-001" has successful tasks 2
    And agent "agent-001" has success rate 0.6666666666666666

  Scenario: Inject and analyze cost data
    Given an audit dashboard with no cost data
    When I inject cost data for agent "agent-002" with total cost 15.50 and 5 tasks
    And I get cost analysis
    Then agent "agent-002" has total cost 15.50
    And agent "agent-002" has tasks 5
    And agent "agent-002" has cost per task 3.1

  Scenario: Rank agents by cost efficiency
    Given an audit dashboard
    When I inject cost data for agent "agent-A" with total cost 10.0 and 5 tasks
    And I inject cost data for agent "agent-B" with total cost 6.0 and 3 tasks
    And I inject cost data for agent "agent-C" with total cost 20.0 and 4 tasks
    And I get cost ranking
    Then the ranking is ["agent-A", "agent-B", "agent-C"]

  Scenario: Register and retrieve agent identity
    Given an audit dashboard
    When I register identity for agent "agent-003" with display name "GPT-4 Agent", model "gpt-4", provider "openai"
    And I get identity for agent "agent-003"
    Then the identity has display name "GPT-4 Agent"
    And the identity has model id "gpt-4"
    And the identity has provider "openai"

  Scenario: Get identity returns None for unregistered agent
    Given an audit dashboard
    When I get identity for agent "unknown-agent"
    Then the identity is None

  Scenario: Generate full report combining performance, identity, and costs
    Given audit events with 2 successful and 1 failed task for agent "agent-100"
    And identity registered for agent "agent-100" as "Claude Agent", model "claude-3", provider "anthropic"
    And cost data for agent "agent-100" with total cost 9.0 and 3 tasks
    When I get full report
    Then agent "agent-100" report contains performance with 3 total tasks and 2 successful tasks
    And agent "agent-100" report contains identity with display name "Claude Agent"
    And agent "agent-100" report contains costs with total cost 9.0

  Scenario: Identify task type strengths
    Given audit events for task type "code_review"
      | agentId  | success |
      | agent-A   | true    |
      | agent-A   | true    |
      | agent-B   | true    |
      | agent-B   | false   |
    When I get task type strengths
    Then task type "code_review" has best agent "agent-A"
    And task type "code_review" has success rate 1.0

  Scenario: Suggest optimal team for task types
    Given audit events showing agent "agent-X" excels at "debugging" with 100% success
    And audit events showing agent "agent-Y" excels at "testing" with 100% success
    When I suggest team for task types ["debugging", "testing"]
    Then the suggested team contains "agent-X"
    And the suggested team contains "agent-Y"

  Scenario: Compare production performance to benchmarks
    Given audit events with agent "agent-500" having 80% success rate
    When I set benchmark data for agent "agent-500" with sweBenchScore 0.65
    And I compare to benchmarks
    Then agent "agent-500" has production success rate 0.8
    And agent "agent-500" has benchmark score 0.65

  Scenario: Generate dashboard summary
    Given audit events with 10 total tasks across 3 agents
    And 2 agents have registered identities
    And 2 agents have cost data
    When I get summary
    Then summary shows 3 agents
    And summary shows 10 total tasks
    And summary shows 2 agents with identity
    And summary shows 2 agents with costs