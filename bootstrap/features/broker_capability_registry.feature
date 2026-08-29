Feature: Anonymous agent capability registry

  Scenario: Registering an agent's capabilities
    Given no agent is registered under reference "agent-42"
    When I register "agent-42" with capabilities {"python": 0.9, "testing": 0.6}
    Then the returned capabilities record has agent_ref "agent-42"
    And the record's core strength is "python"

  Scenario: Core strength ties resolve alphabetically
    Given I register "agent-7" with capabilities {"go": 0.8, "python": 0.8}
    When I retrieve the capabilities for "agent-7"
    Then the record's core strength is "go"

  Scenario: Retrieving an unregistered agent returns nothing
    Given no agent is registered under reference "agent-99"
    When I retrieve the capabilities for "agent-99"
    Then no capabilities record is returned

  Scenario: Finding agents by capability and minimum proficiency
    Given I register "agent-1" with capabilities {"python": 0.9}
    And I register "agent-2" with capabilities {"python": 0.4}
    And I register "agent-3" with capabilities {"java": 0.9}
    When I find agents with capability "python" at minimum proficiency 0.5
    Then the result contains "agent-1"
    And the result does not contain "agent-2"
    And the result does not contain "agent-3"

  Scenario: A single agent covering all needs forms the balanced team
    Given I register "agent-full" with capabilities {"python": 0.9, "testing": 0.8}
    And I register "agent-partial" with capabilities {"python": 0.5}
    When I find a balanced team for needs {"python": 0.7, "testing": 0.7}
    Then the balanced team is ["agent-full"]

  Scenario: Multiple agents combine to form a balanced team when no single agent suffices
    Given I register "agent-backend" with capabilities {"python": 0.9}
    And I register "agent-frontend" with capabilities {"javascript": 0.9}
    When I find a balanced team for needs {"python": 0.7, "javascript": 0.7}
    Then the balanced team contains "agent-backend" and "agent-frontend"

  Scenario: No team can be formed when needs cannot be met
    Given I register "agent-only" with capabilities {"python": 0.5}
    When I find a balanced team for needs {"python": 0.9}
    Then the balanced team is empty

  Scenario: Capability statistics aggregate agent count and average proficiency
    Given I register "agent-a" with capabilities {"python": 0.8}
    And I register "agent-b" with capabilities {"python": 0.4}
    When I get capability statistics
    Then the statistics for "python" show agent_count 2 and avg_proficiency 0.6