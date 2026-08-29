Feature: ACE Enterprise database schema behavior

  Scenario: Creating a playbook applies default counters and timestamps
    Given a new playbook record with playbook_id "pb-checkout-flow", version "1.0.0", domain "checkout", and base_model "gpt-4"
    When the playbook is saved to the database
    Then the playbook's total_tokens is 0
    And the playbook's total_bullets is 0
    And the playbook's created_at and updated_at are set to the current time

  Scenario: Playbook identifiers must be unique
    Given a playbook already exists with playbook_id "pb-checkout-flow"
    When a second playbook is saved with playbook_id "pb-checkout-flow"
    Then the database rejects the save due to a uniqueness constraint violation

  Scenario: Creating a bullet applies default provenance and confidence values
    Given an existing playbook with playbook_id "pb-checkout-flow"
    And a new bullet with bullet_id "bl-001", content "Always validate the cart total before checkout", and section "validation"
    When the bullet is saved to the database
    Then the bullet's helpful_count is 0
    And the bullet's harmful_count is 0
    And the bullet's temporal_confidence is 1.0
    And the bullet's confidence_score is 0.5
    And the bullet's created_by_type is "ai"

  Scenario: Deleting a playbook cascades to its bullets
    Given an existing playbook with playbook_id "pb-checkout-flow"
    And the playbook has a bullet with bullet_id "bl-001"
    When the playbook is deleted
    Then the bullet with bullet_id "bl-001" is also deleted from the database

  Scenario: Bullet lineage relationship type is restricted to known values
    Given two existing bullets with bullet_id "bl-001" and bullet_id "bl-002"
    When a lineage record is saved linking "bl-002" to "bl-001" with relationship_type "supersedes"
    Then the lineage record is saved successfully
    But saving a lineage record with relationship_type "invented_type" is rejected by the database

  Scenario: Experiment log result is restricted to known outcome values
    Given a new experiment log with experiment_id "exp-2026-08-15-001" and playbook_version "1.0.0"
    When the experiment log is saved with result "SUCCESS"
    Then the experiment log is saved successfully
    But saving an experiment log with result "MAYBE" is rejected by the database

  Scenario: Checkpoint records store metrics tied to a playbook version
    Given an existing playbook with playbook_id "pb-checkout-flow" at version "1.0.0"
    When a checkpoint is saved with checkpoint_id "cp-001", trigger "pre_deployment", accuracy 0.92, avg_helpful_ratio 0.85, tasks_processed 500, and avg_latency_ms 120.5
    Then the checkpoint is retrievable by checkpoint_id "cp-001"
    And the checkpoint's retention_policy defaults to "standard"

  Scenario: Regression alerts default to unresolved
    Given a new regression alert for playbook_version "1.0.0" with recent_avg 0.70, baseline_avg 0.85, delta -0.15, p_value 0.02, confidence 0.95, and recommended_action "investigate"
    When the regression alert is saved to the database
    Then the alert's resolved flag is false
    And the alert's resolved_at is null