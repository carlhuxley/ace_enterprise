Feature: Local audit client for development/testing

  Scenario: Create a local audit client with default database location
    Given no database URL is provided
    When I call get_local_audit_client with no arguments
    Then a LocalAuditClient instance is returned
    And it is ready to accept emitted events without error

  Scenario: Create a local audit client with a custom database location
    Given a database URL "sqlite:////tmp/custom_audit.db"
    When I call get_local_audit_client with that database URL
    Then a LocalAuditClient instance is returned
    And events emitted through it are stored at that location

  Scenario: Emit a fully specified audit event successfully
    Given a LocalAuditClient instance
    And an AuditEventCreate with event_type "PATTERN_LEARNED", actor_type "agent", actor_id "tdd-agent", and payload {"pattern_id": "ctx-001"}
    When I call emit with that event
    Then the call returns True

  Scenario: Emit overrides session, playbook, and project identifiers
    Given a LocalAuditClient instance
    And an AuditEventCreate with session_id "session-a", playbook_id "playbook-a", and project_id "project-a"
    When I call emit with session_id "session-b", playbook_id "playbook-b", and project_id "project-c"
    Then the call returns True
    And the stored event reflects session_id "session-b", playbook_id "playbook-b", and project_id "project-c" instead of the original values

  Scenario: Emit a simple event using default actor_type and empty payload
    Given a LocalAuditClient instance
    When I call emit_simple with event_type "PATTERN_LEARNED" and actor_id "tdd-agent" and no payload
    Then the call returns True
    And the stored event has actor_type "agent" and an empty payload

  Scenario: Retrieve audit statistics after emitting events
    Given a LocalAuditClient instance with at least one successfully emitted event
    When I call get_stats
    Then a dictionary of audit statistics is returned

  Scenario: Use the client as a context manager
    Given a database URL for a local audit client
    When I use get_local_audit_client within a "with" statement
    And I emit an event inside the "with" block
    Then the emit call returns True
    And exiting the "with" block completes without error

  Scenario: Close the client explicitly
    Given a LocalAuditClient instance
    When I call close
    Then no error is raised and the client remains unusable for further reasoning about connection state