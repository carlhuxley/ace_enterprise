Feature: ID Generation Utilities

  Scenario: Generate a playbook ID with today's date embedded
    When I call generate_playbook_id on 2025-10-16
    Then the result matches the pattern "pb_20251016_\d{3}"

  Scenario: Generate a bullet ID from a sequence number
    When I call generate_bullet_id with sequence 1
    Then the result equals "ctx-00001"

  Scenario: Generate a bullet ID from a larger sequence number
    When I call generate_bullet_id with sequence 12345
    Then the result equals "ctx-12345"

  Scenario: Generate an experiment ID with today's date embedded
    When I call generate_experiment_id on 2025-10-16
    Then the result matches the pattern "exp_20251016_\d{5}"

  Scenario: Generate a checkpoint ID with today's date embedded
    When I call generate_checkpoint_id on 2025-10-16
    Then the result matches the pattern "ckpt_20251016_\d{3}"

  Scenario: Generate a task ID
    When I call generate_task_id
    Then the result matches the pattern "task_\d{5}"

  Scenario: Generate a confirmation token with the default length
    When I call generate_confirmation_token with no arguments
    Then the result is an 8-character string containing only lowercase letters and digits

  Scenario: Generate a confirmation token with a custom length
    When I call generate_confirmation_token with length 16
    Then the result is a 16-character string containing only lowercase letters and digits