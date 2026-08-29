Feature: Audit chain checkpointing

  Scenario: Creating a checkpoint from a store with recorded events
    Given an audit store containing 5 events
    And the most recent event has id "evt-005" and hash "abc123"
    When I call create_checkpoint with that store
    Then the returned checkpoint has event_count 5
    And the returned checkpoint has last_event_id "evt-005"
    And the returned checkpoint has last_event_hash "abc123"
    And the returned checkpoint has a created_at timestamp

  Scenario: Creating a checkpoint from an empty store
    Given an audit store containing 0 events
    When I call create_checkpoint with that store
    Then the result is None

  Scenario: Writing and reading back a checkpoint
    Given a checkpoint with event_count 5, last_event_id "evt-005", last_event_hash "abc123"
    And an empty checkpoints file path
    When I call write_checkpoint with that checkpoint and path
    And I call read_checkpoints with the same path
    Then the returned list contains exactly 1 checkpoint
    And that checkpoint has event_count 5, last_event_id "evt-005", last_event_hash "abc123"

  Scenario: Appending multiple checkpoints preserves order
    Given a checkpoints file already containing one checkpoint for "evt-005"
    When I write a second checkpoint for "evt-010"
    And I call read_checkpoints with that path
    Then the returned list contains exactly 2 checkpoints
    And the first checkpoint is for "evt-005"
    And the second checkpoint is for "evt-010"

  Scenario: Reading checkpoints from a path that does not exist
    Given a checkpoints file path that has never been written to
    When I call read_checkpoints with that path
    Then the returned list is empty

  Scenario: Verifying checkpoints that all match the live store
    Given a checkpoints file containing a checkpoint for event "evt-005" with hash "abc123"
    And an audit store where event "evt-005" currently has hash "abc123"
    When I call verify_checkpoints with that store and path
    Then the result is valid
    And checkpoints_checked equals 1
    And there are no failures

  Scenario: Verifying a checkpoint whose event hash no longer matches
    Given a checkpoints file containing a checkpoint for event "evt-005" with hash "abc123"
    And an audit store where event "evt-005" currently has hash "def456"
    When I call verify_checkpoints with that store and path
    Then the result is not valid
    And there is 1 failure
    And the failure reason mentions that the hash for "evt-005" changed

  Scenario: Verifying a checkpoint whose event no longer exists
    Given a checkpoints file containing a checkpoint for event "evt-005" with hash "abc123"
    And an audit store where event "evt-005" no longer exists
    When I call verify_checkpoints with that store and path
    Then the result is not valid
    And there is 1 failure
    And the failure reason mentions that event "evt-005" no longer exists in the DB