Feature: Storage Models
  Database model definitions for playbooks, bullets, and experiment records

  Scenario: Playbook model has expected default values
    Given a playbook_id "pb-001" and version "1.0.0" and domain "software"
    When a Playbook model is created
    Then the total_tokens is 0
    And the total_bullets is 0
    And a created_at timestamp is present

  Scenario: Bullet model defaults usage counters to zero
    Given a bullet_id "bullet-001" and content "Use async/await" and section "best_practices"
    When a Bullet model is created
    Then the helpful_count is 0
    And the harmful_count is 0
    And the tags default to an empty list
    And a created_at timestamp is present

  Scenario: Experiment log model records result
    Given an experiment_id "exp-001" and result "SUCCESS" and playbook_updated true
    When an ExperimentLog model is created
    Then the result is "SUCCESS"
    And playbook_updated is true
    And a timestamp is present

  Scenario: Checkpoint model stores accuracy metrics
    Given a checkpoint_id "cp-001" and accuracy 0.92 and tasks_processed 1000
    When a Checkpoint model is created
    Then the accuracy is 0.92
    And the tasks_processed is 1000

  Scenario: Regression alert model records detection values
    Given recent_avg 0.75 and baseline_avg 0.90 and recommended_action "rollback"
    When a RegressionAlert model is created
    Then the delta is negative
    And the recommended_action is "rollback"
    And resolved defaults to false
