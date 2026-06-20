Feature: Context Scorer

  Scenario: Score a bullet with default weights and all dimensions matching
    Given a ContextScorer with default weights
    And a bullet created 30 days ago with teamId "team-alpha", techContext {"python": "3.9"}, and projectIds ["proj-1"]
    And a retrieval context with teamId "team-alpha", techStack {"python": "3.9"}, and projectId "proj-1"
    When the bullet is scored against the context
    Then the combined score should be 1.0
    And the context gaps list should be empty

  Scenario: Score a bullet that has expired
    Given a ContextScorer with default weights
    And a bullet with validUntil set to 10 days ago
    And a retrieval context with queryTimestamp set to now
    When the bullet is scored against the context
    Then the combined score should be 0.0
    And the context gaps list should contain a temporal gap with severity 1.0 and description containing "expired"

  Scenario: Score a bullet that is not yet valid
    Given a ContextScorer with default weights
    And a bullet with validFrom set to 10 days in the future
    And a retrieval context with queryTimestamp set to now
    When the bullet is scored against the context
    Then the combined score should be 0.0
    And the context gaps list should contain a temporal gap with severity 1.0 and description containing "not yet valid"

  Scenario: Score a very old bullet with temporal decay
    Given a ContextScorer with temporalDecayDays set to 365
    And a bullet created 800 days ago
    And a retrieval context with queryTimestamp set to now
    When the bullet is scored against the context
    Then the temporal score should be 0.3
    And the context gaps list should contain a temporal gap with severity 0.5 and description containing "800 days old"

  Scenario: Score a bullet from a different team
    Given a ContextScorer with default weights
    And a bullet with teamId "team-beta"
    And a retrieval context with teamId "team-alpha"
    When the bullet is scored against the context
    Then the team score should be 0.3
    And the context gaps list should contain a team gap with severity 0.4 and description containing "team-beta" and "team-alpha"

  Scenario: Score a bullet with incompatible tech stack
    Given a ContextScorer with default weights
    And a bullet with techContext {"python": "3.9", "django": "4.0"}
    And a retrieval context with techStack {"python": "3.8"}
    When the bullet is scored against the context
    Then the techStack score should be 0.5
    And the context gaps list should contain a techStack gap with description containing "django: required but not in your stack"

  Scenario: Score a bullet with version-compatible tech stack
    Given a ContextScorer with default weights
    And a bullet with techContext {"python": ">=3.8"}
    And a retrieval context with techStack {"python": "3.9"}
    When the bullet is scored against the context
    Then the techStack score should be 1.0
    And the context gaps list should not contain a techStack gap

  Scenario: Score a bullet from a different project but same domain
    Given a ContextScorer with default weights
    And a bullet with projectIds ["proj-2"] and applicableDomains ["ecommerce"]
    And a retrieval context with projectId "proj-1" and domain "ecommerce"
    When the bullet is scored against the context
    Then the project score should be 0.7
    And the context gaps list should be empty for the project dimension

  Scenario: Score a bullet with custom weights
    Given a ContextScorer with weights {"temporal": 0.5, "team": 0.2, "tech_stack": 0.2, "project": 0.1}
    And a bullet with temporal score 1.0, team score 0.5, techStack score 0.5, and project score 0.5
    When the bullet is scored against the context
    Then the combined score should be 0.7

  Scenario: Score domain relevance when bullet has matching domain
    Given a ContextScorer with default weights
    And a bullet with applicableDomains ["fintech", "security"]
    And a retrieval context with domain "fintech"
    When scoreDomain is called with the bullet and context
    Then the domain score should be 1.0
    And the context gap should be None

  Scenario: Score domain relevance when bullet has no matching domain
    Given a ContextScorer with default weights
    And a bullet with applicableDomains ["ecommerce"]
    And a retrieval context with domain "fintech"
    When scoreDomain is called with the bullet and context
    Then the domain score should be 0.3
    And the context gap should have dimension "domain" with severity 0.4

  Scenario: Score with no context information provided
    Given a ContextScorer with default weights
    And a bullet with teamId "team-alpha"
    And a retrieval context with no teamId, no techStack, and no projectId
    When the bullet is scored against the context
    Then the team score should be 0.5
    And the project score should be 0.5