Feature: Audit Query API Service
  As an external caller
  I want to query audit events through a read-only API
  So that I can retrieve and analyze audit log data

  Scenario: Query audit events without filters
    Given an audit store with events
    When I send a GET request to "/events" with no query parameters
    Then I receive an AuditResult response
    And the result contains up to 100 events by default
    And the events are ordered by timestamp descending

  Scenario: Query audit events with time range filters
    Given an audit store with events from multiple time periods
    When I send a GET request to "/events" with startTime "2024-01-01T00:00:00" and endTime "2024-01-31T23:59:59"
    Then I receive an AuditResult response
    And the result contains only events between those timestamps

  Scenario: Query audit events with event type filter
    Given an audit store with multiple event types
    When I send a GET request to "/events" with eventTypes "session.start,session.end"
    Then I receive an AuditResult response
    And the result contains only events of type session.start or session.end

  Scenario: Query audit events with invalid event type
    Given an audit store
    When I send a GET request to "/events" with eventTypes "invalid_type"
    Then I receive a 400 Bad Request response
    And the response detail contains "Invalid event type"

  Scenario: Query audit events with pagination
    Given an audit store with 250 events
    When I send a GET request to "/events" with limit 50 and offset 100
    Then I receive an AuditResult response
    And the result contains 50 events
    And the events start from the 101st event in the ordered sequence

  Scenario: Query audit events with actor and session filters
    Given an audit store with events from multiple actors and sessions
    When I send a GET request to "/events" with actorType "user", actorId "user123", and sessionId "sess456"
    Then I receive an AuditResult response
    And the result contains only events matching all three filters

  Scenario: Get a specific event by ID
    Given an audit store with an event having eventId "evt-12345"
    When I send a GET request to "/events/evt-12345"
    Then I receive the event with eventId "evt-12345"

  Scenario: Get a non-existent event by ID
    Given an audit store without eventId "evt-99999"
    When I send a GET request to "/events/evt-99999"
    Then I receive a 404 Not Found response
    And the response detail contains "Event evt-99999 not found"

  Scenario: Get audit statistics
    Given an audit store with recorded events
    When I send a GET request to "/stats"
    Then I receive a dictionary with audit log statistics

  Scenario: Verify hash chain integrity with valid chain
    Given an audit store with a valid hash chain
    When I send a GET request to "/verify"
    Then I receive a response with chainValid true
    And firstInvalidEvent is null
    And verifiedAt contains an ISO timestamp

  Scenario: Verify hash chain integrity with broken chain
    Given an audit store with a broken hash chain at event "evt-500"
    When I send a GET request to "/verify"
    Then I receive a response with chainValid false
    And firstInvalidEvent is "evt-500"
    And verifiedAt contains an ISO timestamp

  Scenario: Health check endpoint
    Given the audit API is running
    When I send a GET request to "/health"
    Then I receive a response with status "healthy"
    And service "audit-api"