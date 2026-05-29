Feature: Playbook Data Schemas
  Defines validated data structures for bullets, playbooks, and related entities

  Scenario: Create a bullet with required fields only
    Given content "Use async/await for I/O operations" and section "strategies_and_hard_rules"
    When a BulletCreate is constructed with those fields
    Then the content is "Use async/await for I/O operations"
    And the section is "strategies_and_hard_rules"
    And the tags default to an empty list
    And the confidence_score defaults to a value between 0.0 and 1.0

  Scenario: Create a bullet with optional provenance fields
    Given content "Always validate inputs" and section "strategies_and_hard_rules"
    And created_by_model "gpt-4o" and model_provider "openai" and confidence_score 0.85
    When a BulletCreate is constructed with those fields
    Then the created_by_model is "gpt-4o"
    And the model_provider is "openai"
    And the confidence_score is 0.85

  Scenario: A complete Bullet includes id and usage counters
    Given a bullet id "ctx-00001" and content "Cache database queries" and section "strategies_and_hard_rules"
    When a Bullet is constructed
    Then the id is "ctx-00001"
    And the helpful_count is a non-negative integer
    And the harmful_count is a non-negative integer

  Scenario: Content hash is deterministic for the same content
    Given a content string "def validate(data): return schema.parse(data)"
    When the content hash is computed twice
    Then both hashes are identical strings
    And the hash is non-empty

  Scenario: Playbook metadata tracks bullet and token counts
    Given domain "financial_analysis" and total_bullets 342 and total_tokens 125000
    When PlaybookMetadata is constructed
    Then the domain is "financial_analysis"
    And the total_bullets is 342
    And the total_tokens is 125000
