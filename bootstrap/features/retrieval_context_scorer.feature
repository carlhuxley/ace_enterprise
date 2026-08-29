Feature: Context scoring of bullets against request context

  Scenario: A bullet that matches every context dimension receives a near-perfect combined score
    Given a bullet created 5 days ago with no valid_from or valid_until, team_id "platform", tech_context {"python": ">=3.10"}, project_ids ["proj-42"], and applicable_domains ["billing"]
    And a request context with team_id "platform", tech_stack {"python": "3.11"}, project_id "proj-42", domain "billing"
    When the scorer scores the bullet against the context
    Then the combined score is 1.0
    And no context gaps are reported

  Scenario: A pattern that has not yet started its validity window scores zero on the temporal dimension
    Given a bullet with valid_from "2027-01-01" and no valid_until
    And a request context with query_timestamp "2026-08-15"
    When the scorer scores the temporal dimension of the bullet against the context
    Then the temporal score is 0.0
    And a context gap for dimension "temporal" is reported with description "Pattern not yet valid (starts 2027-01-01)" and severity 1.0

  Scenario: An expired pattern scores zero on the temporal dimension
    Given a bullet with valid_until "2025-01-01" and no valid_from
    And a request context with query_timestamp "2026-08-15"
    When the scorer scores the temporal dimension of the bullet against the context
    Then the temporal score is 0.0
    And a context gap for dimension "temporal" is reported with description "Pattern expired (2025-01-01)" and severity 1.0

  Scenario: A pattern from a different team scores lower than one from the caller's team
    Given a bullet with team_id "search-infra"
    And a request context with team_id "platform"
    When the scorer scores the team dimension of the bullet against the context
    Then the team score is 0.3
    And a context gap for dimension "team" is reported with description "Pattern from team 'search-infra', you're in 'platform'" and severity 0.4

  Scenario: Scoring tech stack compatibility when the request context has no known tech stack
    Given a bullet with tech_context {"python": ">=3.10"}
    And a request context with no tech_stack
    When the scorer scores the tech stack dimension of the bullet against the context
    Then the tech stack score is 0.5
    And a context gap for dimension "tech_stack" is reported with description "Tech stack unknown - can't verify compatibility" and severity 0.2

  Scenario: A bullet requiring a newer tool version than the caller has scores lower with an explanatory gap
    Given a bullet with tech_context {"python": ">=3.10"}
    And a request context with tech_stack {"python": "3.8"}
    When the scorer scores the tech stack dimension of the bullet against the context
    Then the tech stack score is 0.0
    And a context gap for dimension "tech_stack" is reported with description "python: need >=3.10, have 3.8" and severity 1.0

  Scenario: A pattern from a different project but the same domain scores better than an unrelated project
    Given a bullet with project_ids ["proj-99"] and applicable_domains ["billing"]
    And a request context with project_id "proj-42" and domain "billing"
    When the scorer scores the project dimension of the bullet against the context
    Then the project score is 0.7
    And no context gap for dimension "project" is reported

  Scenario: A pattern for unrelated domains scores lower with an explanatory gap
    Given a bullet with applicable_domains ["fraud-detection", "risk-scoring"]
    And a request context with domain "billing"
    When the scorer scores the domain dimension of the bullet against the context
    Then the domain score is 0.3
    And a context gap for dimension "domain" is reported with description "Pattern for domains ['fraud-detection', 'risk-scoring'], you're in 'billing'" and severity 0.4