Feature: Human Decision Interface

  Scenario: Getting decision context combines broker recommendation with audit data
    Given a task with id "task-42" requiring specific capabilities
    And audit data containing identities and costs for candidate agents
    When the human requests decision context for that task
    Then the returned context includes the task id "task-42"
    And it includes a broker summary describing the recommendation
    And it includes a list of recommended agents with capability match, whether requirements are met, and success rate
    And it includes the audit data with agent identities and costs

  Scenario: Recording an accepted decision
    When the human records a decision for task "task-42" with decision type "accept" and chosen agent "agent-7"
    Then the result confirms the decision was recorded
    And the result's task id is "task-42"
    And the result includes a non-null decision id

  Scenario: Recording an override decision
    When the human records a decision for task "task-42" with decision type "override" and chosen agent "agent-9" and notes "broker pick was too expensive"
    Then the result confirms the decision was recorded
    And the result's task id is "task-42"

  Scenario: Recording a broadcast decision with no single chosen agent
    When the human records a decision for task "task-42" with decision type "broadcast" and no chosen agent and broadcast list ["agent-3", "agent-5", "agent-9"]
    Then the result confirms the decision was recorded
    And the result's task id is "task-42"

  Scenario: Decision ids increment across successive recorded decisions
    Given no decisions have been recorded yet
    When the human records a first decision for task "task-1"
    And the human records a second decision for task "task-2"
    Then the first decision result has decision id "dec-1"
    And the second decision result has decision id "dec-2"

  Scenario: Retrieving decision history returns all recorded decisions in order
    Given decisions have been recorded for tasks "task-1", "task-2", and "task-3"
    When the human requests the decision history
    Then the history contains exactly those 3 decisions in the order they were recorded

  Scenario: Decision statistics are all zero when no decisions have been recorded
    Given no decisions have been recorded yet
    When the human requests decision statistics
    Then the total decisions is 0
    And accepts, overrides, and broadcasts are all 0
    And the override rate is 0.0

  Scenario: Decision statistics summarize accept, override, and broadcast counts and override rate
    Given 2 "accept" decisions, 1 "override" decision, and 1 "broadcast" decision have been recorded
    When the human requests decision statistics
    Then the total decisions is 4
    And accepts is 2, overrides is 1, and broadcasts is 1
    And the override rate is 0.25