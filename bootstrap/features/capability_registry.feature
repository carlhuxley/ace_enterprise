Feature: Capability Registry
  Anonymous agent capability tracking with T-shaped model support

  Scenario: Register agent with capabilities
    Given a capability registry
    When I register agent "agent-001" with capabilities {"python": 0.8, "rust": 0.6}
    Then the agent "agent-001" can be retrieved
    And the agent has capability "python" with proficiency 0.8
    And the agent has capability "rust" with proficiency 0.6

  Scenario: Update existing agent capabilities
    Given a capability registry
    And agent "agent-002" is registered with capabilities {"java": 0.7}
    When I register agent "agent-002" with capabilities {"java": 0.9, "go": 0.5}
    Then the agent "agent-002" has capability "java" with proficiency 0.9
    And the agent has capability "go" with proficiency 0.5

  Scenario: Identify core strength as highest-rated capability
    Given a capability registry
    When I register agent "agent-003" with capabilities {"python": 0.6, "rust": 0.9, "java": 0.5}
    Then the agent "agent-003" has core strength "rust"

  Scenario: Core strength with tied proficiencies returns alphabetically first
    Given a capability registry
    When I register agent "agent-004" with capabilities {"rust": 0.8, "python": 0.8, "go": 0.7}
    Then the agent "agent-004" has core strength "python"

  Scenario: Core strength is None for agent with no capabilities
    Given a capability registry
    When I register agent "agent-005" with capabilities {}
    Then the agent "agent-005" has core strength None

  Scenario: Find agents by capability with minimum proficiency
    Given a capability registry
    And agent "agent-101" is registered with capabilities {"python": 0.9}
    And agent "agent-102" is registered with capabilities {"python": 0.6, "rust": 0.8}
    And agent "agent-103" is registered with capabilities {"python": 0.4}
    When I search for capability "python" with minimum proficiency 0.5
    Then the results contain ["agent-101", "agent-102"]

  Scenario: Find agents by capability with no minimum proficiency
    Given a capability registry
    And agent "agent-201" is registered with capabilities {"docker": 0.3}
    And agent "agent-202" is registered with capabilities {"docker": 0.9}
    When I search for capability "docker" with minimum proficiency 0.0
    Then the results contain ["agent-201", "agent-202"]

  Scenario: Find no agents when capability does not exist
    Given a capability registry
    And agent "agent-301" is registered with capabilities {"python": 0.8}
    When I search for capability "haskell" with minimum proficiency 0.5
    Then the results are empty

  Scenario: Find balanced team with single agent covering all needs
    Given a capability registry
    And agent "agent-401" is registered with capabilities {"python": 0.9, "rust": 0.8, "docker": 0.7}
    And agent "agent-402" is registered with capabilities {"python": 0.6}
    When I find a balanced team for needs {"python": 0.8, "rust": 0.7}
    Then the team contains ["agent-401"]

  Scenario: Find balanced team requiring multiple agents
    Given a capability registry
    And agent "agent-501" is registered with capabilities {"python": 0.9}
    And agent "agent-502" is registered with capabilities {"rust": 0.8}
    And agent "agent-503" is registered with capabilities {"go": 0.7}
    When I find a balanced team for needs {"python": 0.8, "rust": 0.7}
    Then the team size is 2
    And the team covers all required capabilities

  Scenario: Find balanced team returns empty when needs cannot be met
    Given a capability registry
    And agent "agent-601" is registered with capabilities {"python": 0.5}
    When I find a balanced team for needs {"python": 0.9, "rust": 0.8}
    Then the team is empty

  Scenario: Find balanced team with empty needs returns empty team
    Given a capability registry
    And agent "agent-701" is registered with capabilities {"python": 0.8}
    When I find a balanced team for needs {}
    Then the team is empty

  Scenario: Get capability statistics across registered agents
    Given a capability registry
    And agent "agent-801" is registered with capabilities {"python": 0.8, "rust": 0.6}
    And agent "agent-802" is registered with capabilities {"python": 0.6, "go": 0.9}
    And agent "agent-803" is registered with capabilities {"python": 0.9}
    When I get capability statistics
    Then capability "python" has agent_count 3 and avg_proficiency 0.7666666666666667
    And capability "rust" has agent_count 1 and avg_proficiency 0.6
    And capability "go" has agent_count 1 and avg_proficiency 0.9

  Scenario: Get empty statistics when no agents registered
    Given a capability registry
    When I get capability statistics
    Then the statistics are empty

  Scenario: Retrieve non-existent agent returns None
    Given a capability registry
    When I get agent "agent-999"
    Then the result is None