Feature: ID Generator
  Generates unique identifiers for ACE Enterprise entities following PRD naming conventions

  Scenario: Generate playbook ID
    When I call generate_playbook_id
    Then the result matches the pattern "pb_YYYYMMDD_NNN"
    And the date portion reflects the current UTC date
    And the numeric suffix is zero-padded to 3 digits
    And the numeric suffix is between 001 and 999

  Scenario: Generate bullet ID with sequence number
    When I call generate_bullet_id with sequence 1
    Then the result is "ctx-00001"

  Scenario: Generate bullet ID with large sequence number
    When I call generate_bullet_id with sequence 12345
    Then the result is "ctx-12345"

  Scenario: Generate experiment ID
    When I call generate_experiment_id
    Then the result matches the pattern "exp_YYYYMMDD_NNNNN"
    And the date portion reflects the current UTC date
    And the numeric suffix is zero-padded to 5 digits
    And the numeric suffix is between 00001 and 99999

  Scenario: Generate checkpoint ID
    When I call generate_checkpoint_id
    Then the result matches the pattern "ckpt_YYYYMMDD_NNN"
    And the date portion reflects the current UTC date
    And the numeric suffix is zero-padded to 3 digits
    And the numeric suffix is between 001 and 999

  Scenario: Generate task ID
    When I call generate_task_id
    Then the result matches the pattern "task_NNNNN"
    And the numeric suffix is zero-padded to 5 digits
    And the numeric suffix is between 00001 and 99999

  Scenario: Generate confirmation token with default length
    When I call generate_confirmation_token
    Then the result is 8 characters long
    And the result contains only lowercase letters and digits

  Scenario: Generate confirmation token with custom length
    When I call generate_confirmation_token with length 16
    Then the result is 16 characters long
    And the result contains only lowercase letters and digits