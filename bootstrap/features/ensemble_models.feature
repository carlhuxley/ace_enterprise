Feature: Ensemble consensus data models

  Scenario: Creating a vote with valid confidence succeeds
    Given a model identifier "gpt-4" and a confidence score of 0.85
    When a vote is cast with type "approve" and reasoning "clear and actionable"
    Then the vote is created successfully with confidence 0.85

  Scenario: Creating a vote with out-of-range confidence is rejected
    Given a model identifier "claude-3" and a confidence score of 1.5
    When a vote is cast with type "approve" and reasoning "strong candidate"
    Then a ValueError is raised stating confidence must be between 0.0 and 1.0

  Scenario: Adding votes from different models to a bullet accumulates them
    Given a proposed bullet with content "Always validate input" in section "strategies_and_hard_rules"
    When a vote from model "gpt-4" with type "approve" and confidence 0.9 is added
    And a vote from model "claude-3" with type "reject" and confidence 0.6 is added
    Then the bullet's vote counts show 1 approve and 1 reject
    And the bullet's approval rate is 0.5
    And the bullet's average confidence is 0.75

  Scenario: Adding a second vote from the same model without allowing update is rejected
    Given a proposed bullet with content "Use retries on network calls" in section "code_snippets"
    And a vote from model "gpt-4" with type "approve" and confidence 0.8 has already been added
    When a second vote from model "gpt-4" with type "reject" and confidence 0.7 is added without allowing updates
    Then a ValueError is raised stating the model already voted on this bullet

  Scenario: Adding a second vote from the same model with update allowed replaces the prior vote
    Given a proposed bullet with content "Cache expensive computations" in section "domain_knowledge"
    And a vote from model "gpt-4" with type "reject" and confidence 0.4 has already been added
    When a second vote from model "gpt-4" with type "approve" and confidence 0.9 is added with updates allowed
    Then the bullet has exactly one vote recorded for model "gpt-4"
    And that vote has type "approve" and confidence 0.9

  Scenario: A bullet with a closely split vote is reported as contested
    Given a proposed bullet with content "Prefer composition over inheritance" in section "strategies_and_hard_rules"
    And a vote from model "gpt-4" with type "approve" and confidence 0.7 has already been added
    And a vote from model "claude-3" with type "reject" and confidence 0.6 has already been added
    When the bullet's contested status is checked with default thresholds
    Then the bullet is reported as contested

  Scenario: A bullet with only one vote is never reported as contested
    Given a proposed bullet with content "Log all errors with context" in section "troubleshooting_tips"
    And a vote from model "gpt-4" with type "approve" and confidence 0.9 has already been added
    When the bullet's contested status is checked with default thresholds
    Then the bullet is reported as not contested

  Scenario: Vote aggregation results compute an approval percentage from counts
    Given voting results recording 10 total bullets with 7 approved, 2 rejected, and 1 pending
    When the approval percentage is calculated
    Then the approval percentage is 70.0