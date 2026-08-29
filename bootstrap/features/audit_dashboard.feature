Feature: Audit Dashboard analysis

  Scenario: Calculating agent performance from completed cycles
    Given audit events containing 3 "CYCLE_COMPLETED" events for actor "agent-1", where 2 have payload success true and 1 has success false
    When I request the agent performance
    Then the performance for "agent-1" shows 3 total tasks, 2 successful tasks, and a success rate of 0.666...

  Scenario: Agent performance ignores non-completion events
    Given audit events containing 1 "CYCLE_COMPLETED" event for actor "agent-2" with success true and 2 events of type "TASK_STARTED" for actor "agent-2"
    When I request the agent performance
    Then the performance for "agent-2" shows 1 total task and 1 successful task

  Scenario: Injecting and analyzing cost data
    Given cost data mapping "agent-1" to a total cost of 10.0 over 5 tasks
    When I inject that cost data and request the cost analysis
    Then the cost analysis for "agent-1" shows total cost 10.0, 5 tasks, and a cost per task of 2.0

  Scenario: Ranking agents by cost efficiency
    Given cost data mapping "agent-cheap" to a cost per task of 1.0 and "agent-expensive" to a cost per task of 5.0
    When I inject that cost data and request the cost ranking
    Then the ranking lists "agent-cheap" before "agent-expensive"

  Scenario: Registering and retrieving agent identity
    Given an identity with display name "Claude Sonnet", model id "claude-sonnet-5", and provider "anthropic"
    When I register that identity for agent reference "agent-1" and then request the identity for "agent-1"
    Then the returned identity has display name "Claude Sonnet", model id "claude-sonnet-5", and provider "anthropic"

  Scenario: Requesting identity for an unregistered agent
    Given no identity has been registered for "agent-unknown"
    When I request the identity for "agent-unknown"
    Then no identity is returned

  Scenario: Full report combines performance, identity, and costs
    Given audit events showing "agent-1" completed 2 tasks successfully, a registered identity for "agent-1", and cost data for "agent-1"
    When I request the full report
    Then the entry for "agent-1" includes performance, identity, and costs sections

  Scenario: Suggesting a team based on task type strengths
    Given audit events showing "agent-1" succeeds most often at task type "bugfix" and "agent-2" succeeds most often at task type "refactor"
    When I request a suggested team for task types "bugfix" and "refactor"
    Then the suggested team contains "agent-1" and "agent-2"

  Scenario: Comparing production performance to benchmark scores
    Given "agent-1" has a production success rate of 0.8 and benchmark data with a swe_bench_score of 0.75
    When I set that benchmark data and request the benchmark comparison
    Then the comparison for "agent-1" shows production success rate 0.8 and benchmark score 0.75

  Scenario: Generating a summary of dashboard data
    Given audit events for "agent-1" and "agent-2", registered identities for "agent-1", and cost data for "agent-2"
    When I request the summary
    Then the summary lists "agent-1" and "agent-2" as agents, the correct total task count, "agent-1" under agents with identity, and "agent-2" under agents with costs