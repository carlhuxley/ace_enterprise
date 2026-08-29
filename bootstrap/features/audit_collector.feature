Feature: Audit event collector

  As an ACE agent
  I want to submit audit events to the collector service
  So that they are durably recorded in the audit log

  Scenario: Submitting a valid audit event with a valid API key
    Given the collector service is running
    And I have a valid API key
    When I send a POST request to "/events" with a valid audit event payload
    Then the response status code is 202
    And the response body contains "status" equal to "accepted"
    And the response body contains an "event_id" field

  Scenario: Submitting an audit event without an API key
    Given the collector service is running
    When I send a POST request to "/events" with a valid audit event payload and no API key
    Then the response indicates the request was not authorized

  Scenario: Submitting an audit event with an invalid API key
    Given the collector service is running
    And I have an API key that is not valid
    When I send a POST request to "/events" with a valid audit event payload
    Then the response indicates the request was not authorized

  Scenario: Submitting a malformed audit event
    Given the collector service is running
    And I have a valid API key
    When I send a POST request to "/events" with a payload that does not match the expected audit event schema
    Then the response status code is 422

  Scenario: Audit store fails to persist the event
    Given the collector service is running
    And I have a valid API key
    And the audit store is unable to persist events
    When I send a POST request to "/events" with a valid audit event payload
    Then the response status code is 500
    And the response body does not expose internal error details

  Scenario: Requesting the health check endpoint
    Given the collector service is running
    When I send a GET request to "/health"
    Then the response status code is 200
    And the response body contains "status" equal to "healthy"
    And the response body contains "service" equal to "audit-collector"

  Scenario: Attempting to read or query audit events
    Given the collector service is running
    And I have a valid API key
    When I send a GET request to "/events"
    Then the response status code is 405

  Scenario: Attempting to use a disallowed HTTP method on the events endpoint
    Given the collector service is running
    And I have a valid API key
    When I send a PUT request to "/events" with a valid audit event payload
    Then the response status code is 405