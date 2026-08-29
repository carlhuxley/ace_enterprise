Feature: Data validation schemas for playbook bullets, experiments, and checkpoints

  Scenario: Creating a bullet with only required fields applies sensible defaults
    Given a BulletCreate is constructed with content "Always validate user input" and section "strategies_and_hard_rules"
    When the schema is built
    Then the "tags" field defaults to an empty list
    And the "created_by_type" field defaults to "ai"
    And the "confidence_score" field defaults to 0.5

  Scenario: Bullet confidence score outside the valid range is rejected
    Given a BulletCreate is constructed with content "Use retries" and section "troubleshooting" and confidence_score 1.5
    When the schema is validated
    Then validation fails because confidence_score must be between 0.0 and 1.0

  Scenario: BulletFeedback only accepts known feedback tags
    Given a BulletFeedback is constructed with bullet_id "ctx-00001" and tag "excellent"
    When the schema is validated
    Then validation fails because "tag" must be one of "helpful", "harmful", or "neutral"

  Scenario: DeltaBullet exposes a stable content hash for deduplication
    Given a DeltaBullet is constructed with section "code_snippets" and content "  print('hello world')  "
    When the "content_hash" property is read
    Then it returns a 16-character hexadecimal string
    And reading "content_hash" again for a DeltaBullet with content "print('hello world')" returns the same value

  Scenario: CheckpointMetrics rejects a non-positive average latency
    Given a CheckpointMetrics is constructed with accuracy 0.9, avg_helpful_ratio 0.8, tasks_processed 100, and avg_latency_ms 0
    When the schema is validated
    Then validation fails because avg_latency_ms must be greater than 0

  Scenario: RollbackRequest requires a confirmation token
    Given a RollbackRequest payload is built without a "confirmation_token" field
    When the schema is validated
    Then validation fails because "confirmation_token" is required

  Scenario: ExperimentLogCreate composes nested task, generator, and environment schemas
    Given a valid TaskInput, GeneratorOutput, and EnvironmentFeedback payload
    And a playbook_version of "1.2.3"
    When an ExperimentLogCreate is constructed from these values
    Then the resulting object exposes "task", "generator", and "environment" as populated nested objects

  Scenario: RegressionAlert only accepts known recommended actions
    Given a RegressionAlert payload with recommended_action "escalate"
    When the schema is validated
    Then validation fails because "recommended_action" must be one of "rollback", "investigate", or "ignore"