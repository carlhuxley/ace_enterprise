Feature: Append-only audit event store with hash chain integrity

  Scenario: Appending an event populates hash chain fields
    Given an empty audit store
    When I append an audit event with event_type "AGENT_ACTION", actor_type "agent", and actor_id "agent-42"
    Then the returned event has a non-empty event_hash
    And the returned event has a prev_hash of null

  Scenario: Appending a second event links it to the previous event's hash
    Given an audit store containing one previously appended event with event_hash "abc123"
    When I append a new audit event with event_type "USER_LOGIN", actor_type "user", and actor_id "user-7"
    Then the returned event's prev_hash equals "abc123"
    And the returned event has a new, different event_hash

  Scenario: Querying an empty store returns no events
    Given an empty audit store
    When I query for events with no filters
    Then the result contains 0 events
    And total_count is 0
    And has_more is false
    And chain_valid is true

  Scenario: Querying returns events matching actor and time filters
    Given an audit store containing 3 events for actor_id "agent-42" and 2 events for actor_id "user-7"
    When I query for events with actor_id "agent-42"
    Then the result contains 3 events
    And every returned event has actor_id "agent-42"

  Scenario: Querying with pagination indicates more results are available
    Given an audit store containing 10 appended events
    When I query for events with limit 5 and offset 0
    Then the result contains 5 events
    And total_count is 10
    And has_more is true

  Scenario: Verifying an intact hash chain reports it as valid
    Given an audit store containing 5 sequentially appended events with no tampering
    When I verify the full chain
    Then the chain is reported as valid
    And no invalid event_id is returned

  Scenario: Verifying a tampered hash chain reports the first broken event
    Given an audit store containing 5 sequentially appended events
    And the payload of the 3rd event has been altered directly in the database, invalidating its hash
    When I verify the full chain
    Then the chain is reported as invalid
    And the returned event_id matches the 3rd event

  Scenario: Retrieving store statistics summarizes event counts and time range
    Given an audit store containing 4 events of type "AGENT_ACTION" and 2 events of type "USER_LOGIN"
    When I request store statistics
    Then total_events is 6
    And events_by_type shows 4 for "AGENT_ACTION" and 2 for "USER_LOGIN"
    And oldest_event and newest_event reflect the timestamps of the appended events