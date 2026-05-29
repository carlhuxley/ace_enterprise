Feature: Audit Store
  Append-only event log with hash-chain integrity verification

  Scenario: First appended event has no previous hash
    Given an empty audit store
    When an event is appended with event_id "evt-001" and type "AGENT_CREATED"
    Then the returned event has no prev_hash
    And the returned event has a non-empty event_hash

  Scenario: Second appended event links to the first via prev_hash
    Given an audit store with one event whose hash is "abc123"
    When a second event is appended
    Then the returned event has prev_hash equal to "abc123"
    And the returned event has a different event_hash

  Scenario: Query returns events with pagination metadata
    Given an audit store with 5 events
    When events are queried with limit 2 and offset 0
    Then 2 events are returned
    And has_more is true
    And total_count is 5

  Scenario: Verify chain passes for an unmodified store
    Given an audit store with 3 properly chained events
    When the full chain is verified
    Then the result indicates the chain is valid

  Scenario: Verify chain fails when an event hash is corrupted
    Given an audit store with 3 events where the second event hash has been altered
    When the full chain is verified
    Then the result indicates the chain is invalid
