Feature: Audit event schemas

  Scenario: Creating an audit event with required fields
    Given an event type "knowledge_added", actor type "human", and actor id "carlhuxley@gmail.com"
    When an AuditEvent is constructed with event_id "evt-001" and these values
    Then the event's timestamp defaults to the current UTC time
    And the event's session_id, playbook_id, and project_id default to null
    And the event's payload defaults to an empty object
    And the event's prev_hash and event_hash default to null

  Scenario: Computing a hash for an audit event
    Given an AuditEvent with event_id "evt-002", event_type "pattern_learned", actor_type "agent", actor_id "architect-1", and payload {"pattern": "retry-on-timeout"}
    When compute_hash is called
    Then a 64-character hexadecimal SHA-256 digest string is returned
    And calling compute_hash again on the same unmodified event returns the same digest

  Scenario: Hash is stable regardless of timestamp timezone representation
    Given two AuditEvent instances with identical field values except one has a timezone-aware UTC timestamp and the other has the equivalent naive timestamp
    When compute_hash is called on each
    Then both events produce the same digest

  Scenario: Changing the payload changes the hash
    Given an AuditEvent with payload {"result": "success"}
    And its computed hash is recorded
    When a new AuditEvent is created identical except payload {"result": "failure"}
    And its hash is computed
    Then the two hashes are different

  Scenario: Building a hash chain links an event to its predecessor
    Given an AuditEvent with event_id "evt-003" and no prev_hash
    And a known previous event hash "a1b2c3..."
    When with_hash_chain is called with prev_hash "a1b2c3..."
    Then a new AuditEvent is returned with prev_hash set to "a1b2c3..."
    And event_hash is set to a hash computed including that prev_hash
    And the original event instance remains unmodified

  Scenario: Creating an event via AuditEventCreate without hash chain fields
    When an AuditEventCreate is constructed with event_type "agent_started", actor_type "system", actor_id "system"
    Then no event_id, timestamp, prev_hash, or event_hash fields are present on the object
    And session_id, playbook_id, and project_id default to null
    And payload defaults to an empty object

  Scenario: Querying audit events with default pagination and ordering
    When an AuditQuery is constructed with no arguments
    Then limit defaults to 100
    And offset defaults to 0
    And order_by defaults to "timestamp"
    And order_desc defaults to true
    And start_time, end_time, event_types, actor_type, actor_id, session_id, playbook_id, and project_id default to null

  Scenario: AuditQuery rejects an out-of-range limit
    When an AuditQuery is constructed with limit 1500
    Then construction fails with a validation error

  Scenario: Representing a query result with chain integrity
    Given a list of AuditEvent objects, a total_count of 42, and has_more true
    When an AuditResult is constructed without specifying chain_valid
    Then chain_valid defaults to true
    And the events, total_count, and has_more fields match the given values