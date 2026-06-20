Feature: Human Decision Interface
  As a human decision maker
  I want to see full context including broker recommendations and audit data
  So that I can make informed agent assignment decisions

  Scenario: Get decision context with broker recommendations and audit data
    Given a broker advisor that recommends agents based on capabilities
    And audit data containing agent identities and costs
    And task requirements with taskId "task-001" requiring capability "python"
    When I get the decision context for the task requirements
    Then the context contains taskId "task-001"
    And the context contains a broker summary
    And the context contains a list of recommendations with agentRef, capabilityMatch, meetsRequirements, and successRate
    And the context contains the audit data
    And the context has a createdAt timestamp

  Scenario: Record a human decision to accept broker recommendation
    Given a human decision interface
    And a human decision for taskId "task-002" choosing agent "agent-A" with decisionType "accept"
    When I record the decision
    Then the result shows recorded is True
    And the result contains taskId "task-002"
    And the result contains a decisionId "dec-1"

  Scenario: Record a human decision to override broker recommendation
    Given a human decision interface
    And a human decision for taskId "task-003" choosing agent "agent-B" with decisionType "override" and notes "Better cost profile"
    When I record the decision
    Then the result shows recorded is True
    And the result contains taskId "task-003"
    And the result contains a decisionId

  Scenario: Record a broadcast decision with no specific agent
    Given a human decision interface
    And a human decision for taskId "task-004" with chosenAgentRef None, decisionType "broadcast", and broadcastTo list containing "agent-X" and "agent-Y"
    When I record the decision
    Then the result shows recorded is True
    And the result contains taskId "task-004"

  Scenario: Retrieve decision history after recording multiple decisions
    Given a human decision interface
    And I have recorded a decision for taskId "task-005" with decisionType "accept"
    And I have recorded a decision for taskId "task-006" with decisionType "override"
    And I have recorded a decision for taskId "task-007" with decisionType "broadcast"
    When I get the decision history
    Then the history contains 3 decisions
    And the history includes the decision for taskId "task-005"
    And the history includes the decision for taskId "task-006"
    And the history includes the decision for taskId "task-007"

  Scenario: Get decision statistics with no decisions recorded
    Given a human decision interface with no recorded decisions
    When I get the decision stats
    Then the stats show totalDecisions is 0
    And the stats show accepts is 0
    And the stats show overrides is 0
    And the stats show broadcasts is 0
    And the stats show overrideRate is 0.0

  Scenario: Get decision statistics after recording mixed decision types
    Given a human decision interface
    And I have recorded 3 decisions with decisionType "accept"
    And I have recorded 2 decisions with decisionType "override"
    And I have recorded 1 decision with decisionType "broadcast"
    When I get the decision stats
    Then the stats show totalDecisions is 6
    And the stats show accepts is 3
    And the stats show overrides is 2
    And the stats show broadcasts is 1
    And the stats show overrideRate is 0.3333333333333333