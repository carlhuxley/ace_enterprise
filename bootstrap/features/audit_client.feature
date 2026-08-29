Feature: Write-only audit event emission

  Scenario: Successfully emit an audit event
    Given an AuditClient configured with endpoint "http://ace-audit:8081"
    And the audit service accepts POST requests to "/events" with status 202
    When the client emits an event of type "PATTERN_LEARNED" with actor_id "tdd-agent-v1" and payload {"pattern_id": "ctx-00042", "content_hash": "abc123"}
    Then the emit call returns True

  Scenario: Audit service rejects the event
    Given an AuditClient configured with endpoint "http://ace-audit:8081"
    And the audit service responds to POST "/events" with status 400
    When the client emits an event of type "PATTERN_LEARNED" with actor_id "tdd-agent-v1"
    Then the emit call returns False

  Scenario: Emit times out in async mode
    Given an AuditClient configured with async_mode True
    And the audit service does not respond before the configured timeout
    When the client emits an event of type "PATTERN_LEARNED" with actor_id "tdd-agent-v1"
    Then the emit call returns True

  Scenario: Emit times out in synchronous mode
    Given an AuditClient configured with async_mode False
    And the audit service does not respond before the configured timeout
    When the client emits an event of type "PATTERN_LEARNED" with actor_id "tdd-agent-v1"
    Then the emit call returns False

  Scenario: Network error while emitting in async mode
    Given an AuditClient configured with async_mode True
    And the audit service is unreachable due to a network error
    When the client emits an event of type "PATTERN_LEARNED" with actor_id "tdd-agent-v1"
    Then the emit call returns True

  Scenario: Convenience method emits an event without an explicit AuditEventCreate object
    Given an AuditClient configured with endpoint "http://ace-audit:8081"
    And the audit service accepts POST requests to "/events" with status 202
    When the client calls emit_simple with event_type "PATTERN_LEARNED", actor_id "tdd-agent-v1", and payload {"key": "value"}
    Then the emit call returns True

  Scenario: No-op audit client accepts events without sending them
    Given a NoOpAuditClient
    When the client emits an event of type "PATTERN_LEARNED" with actor_id "tdd-agent-v1"
    Then the emit call returns True
    And no HTTP request is sent to any audit service

  Scenario: Factory returns a no-op client when audit is disabled
    Given the environment variable "AUDIT_DISABLED" is set to "true"
    When get_audit_client is called
    Then the returned client accepts and discards events without sending them over HTTP