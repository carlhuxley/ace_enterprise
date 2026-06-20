Feature: Local Audit Client
  A local audit client that writes audit events to a SQLite database for development and testing

  Scenario: Emit a simple audit event with minimal parameters
    Given a local audit client is initialized
    When emitSimple is called with eventType "PATTERN_LEARNED" and actorId "tdd-agent"
    Then the method returns True

  Scenario: Emit a simple audit event with payload
    Given a local audit client is initialized
    When emitSimple is called with eventType "PATTERN_LEARNED", actorId "tdd-agent", and payload {"pattern_id": "ctx-001"}
    Then the method returns True

  Scenario: Emit a simple audit event with all optional parameters
    Given a local audit client is initialized
    When emitSimple is called with eventType "PATTERN_LEARNED", actorId "tdd-agent", payload {"pattern_id": "ctx-001"}, actorType "system", sessionId "sess-123", playbookId "play-456", and projectId "proj-789"
    Then the method returns True

  Scenario: Emit an audit event using AuditEventCreate object
    Given a local audit client is initialized
    And an AuditEventCreate object with eventType "PATTERN_LEARNED", actorType "agent", and actorId "tdd-agent"
    When emit is called with the AuditEventCreate object
    Then the method returns True

  Scenario: Emit an audit event with override parameters
    Given a local audit client is initialized
    And an AuditEventCreate object with eventType "PATTERN_LEARNED", actorType "agent", actorId "tdd-agent", and sessionId "original-session"
    When emit is called with the AuditEventCreate object and sessionId override "override-session"
    Then the method returns True

  Scenario: Get audit statistics after emitting events
    Given a local audit client is initialized
    When emitSimple is called with eventType "PATTERN_LEARNED" and actorId "tdd-agent"
    And getStats is called
    Then a dictionary with statistics is returned

  Scenario: Use local audit client as context manager
    Given a local audit client is obtained using getLocalAuditClient
    When the client is used as a context manager
    And emitSimple is called with eventType "PATTERN_LEARNED" and actorId "tdd-agent" inside the context
    Then the method returns True
    And the context exits without error

  Scenario: Initialize local audit client with custom database URL
    Given a custom database URL "sqlite:///custom/path/audit.db"
    When getLocalAuditClient is called with the custom database URL
    Then a LocalAuditClient instance is returned