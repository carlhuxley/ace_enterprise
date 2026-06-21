Feature: Audit Client
  Write-only audit client for emitting audit events to an audit service

  Scenario: Initialize audit client with explicit endpoint
    Given an audit client is created with endpoint "http://audit-service:9000"
    When the client is queried for its endpoint
    Then the endpoint should be "http://audit-service:9000"

  Scenario: Initialize audit client with environment variable
    Given the environment variable "AUDIT_ENDPOINT" is set to "http://env-audit:8080"
    When an audit client is created with no explicit endpoint
    Then the client endpoint should be "http://env-audit:8080"

  Scenario: Emit audit event successfully
    Given an audit client with endpoint "http://audit-service:8081"
    And an AuditEventCreate with eventType "PATTERN_LEARNED", actorType "agent", actorId "test-agent-1", and payload {"patternId": "ctx-001"}
    When the client emits the event
    And the audit service responds with status code 202
    Then the emit method should return True

  Scenario: Emit audit event that is rejected
    Given an audit client with endpoint "http://audit-service:8081"
    And an AuditEventCreate with eventType "PATTERN_LEARNED", actorType "agent", actorId "test-agent-2", and payload {}
    When the client emits the event
    And the audit service responds with status code 400
    Then the emit method should return False

  Scenario: Emit simple audit event with convenience method
    Given an audit client with endpoint "http://audit-service:8081"
    When emitSimple is called with eventType "PATTERN_LEARNED", actorId "agent-123", and payload {"key": "value"}
    And the audit service responds with status code 202
    Then the emitSimple method should return True

  Scenario: Emit event with context overrides
    Given an audit client with endpoint "http://audit-service:8081"
    And an AuditEventCreate with eventType "PATTERN_LEARNED", actorType "agent", actorId "agent-456", sessionId "session-1", and payload {}
    When the client emits the event with sessionId "session-override", playbookId "playbook-99", and projectId "project-42"
    And the audit service responds with status code 202
    Then the emit method should return True

  Scenario: Emit event in async mode with timeout
    Given an audit client with endpoint "http://audit-service:8081" and asyncMode True
    And an AuditEventCreate with eventType "PATTERN_LEARNED", actorType "agent", actorId "agent-789", and payload {}
    When the client emits the event
    And the request times out
    Then the emit method should return True

  Scenario: Emit event in sync mode with timeout
    Given an audit client with endpoint "http://audit-service:8081" and asyncMode False
    And an AuditEventCreate with eventType "PATTERN_LEARNED", actorType "agent", actorId "agent-999", and payload {}
    When the client emits the event
    And the request times out
    Then the emit method should return False

  Scenario: Use audit client as context manager
    Given an audit client with endpoint "http://audit-service:8081"
    When the client is used as a context manager
    Then the client should be properly initialized on enter
    And the client should be properly closed on exit

  Scenario: NoOp audit client always accepts events
    Given a NoOpAuditClient is created
    And an AuditEventCreate with eventType "PATTERN_LEARNED", actorType "agent", actorId "noop-agent", and payload {"testData": "data"}
    When the NoOpAuditClient emits the event
    Then the emit method should return True

  Scenario: Get audit client with disabled audit
    Given the environment variable "AUDIT_DISABLED" is set to "true"
    When getAuditClient is called
    Then a NoOpAuditClient should be returned

  Scenario: Get audit client with no endpoint configured
    Given the environment variable "AUDIT_ENDPOINT" is not set
    When getAuditClient is called
    Then a NoOpAuditClient should be returned

  Scenario: Get audit client with endpoint configured
    Given the environment variable "AUDIT_ENDPOINT" is set to "http://configured-audit:8081"
    And the environment variable "AUDIT_DISABLED" is not set to "true"
    When getAuditClient is called
    Then an AuditClient should be returned with endpoint "http://configured-audit:8081"
