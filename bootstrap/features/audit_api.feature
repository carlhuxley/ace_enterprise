Feature: Audit Query API

  Scenario: Querying events without filters returns paginated results
    Given a valid API key
    When I send a GET request to "/events"
    Then the response status is 200
    And the response body contains an audit result with events, a total count, and pagination info

  Scenario: Querying events with an invalid event type returns a client error
    Given a valid API key
    When I send a GET request to "/events" with query parameter "event_types" set to "not_a_real_type"
    Then the response status is 400
    And the response body contains a detail message about the invalid event type

  Scenario: Querying events without an API key is rejected
    Given no API key is provided
    When I send a GET request to "/events"
    Then the response is rejected with an authentication error

  Scenario: Retrieving a specific event by ID that exists
    Given a valid API key
    And an audit event exists with ID "evt-12345"
    When I send a GET request to "/events/evt-12345"
    Then the response status is 200
    And the response body contains the event with ID "evt-12345"

  Scenario: Retrieving a specific event by ID that does not exist
    Given a valid API key
    When I send a GET request to "/events/nonexistent-id"
    Then the response status is 404
    And the response body contains a detail message that the event was not found

  Scenario: Retrieving audit log statistics
    Given a valid API key
    When I send a GET request to "/stats"
    Then the response status is 200
    And the response body contains summary statistics about the audit log

  Scenario: Verifying the audit log hash chain integrity
    Given a valid API key
    When I send a GET request to "/verify"
    Then the response status is 200
    And the response body contains "chain_valid", "checkpoint_valid", "checkpoints_checked", and "verified_at" fields

  Scenario: Checking service health without authentication
    Given no API key is provided
    When I send a GET request to "/health"
    Then the response status is 200
    And the response body is {"status": "healthy", "service": "audit-api"}