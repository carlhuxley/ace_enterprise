Feature: Audit Event Collector Service
  As an ACE agent
  I want to submit audit events to the collector
  So that they can be stored in the immutable audit log

  Scenario: Successfully submit a valid audit event
    Given an audit collector application with an audit store
    When I POST a valid audit event to "/events" with fields:
      | field       | value                                      |
      | eventType   | user.login                                 |
      | timestamp   | 2024-01-15T10:30:00Z                       |
      | actor       | user-123                                   |
      | resource    | system                                     |
      | action      | authenticate                               |
      | outcome     | success                                    |
    Then the response status code should be 202
    And the response should contain "status" with value "accepted"
    And the response should contain "eventId"

  Scenario: Collector returns minimal response on successful event submission
    Given an audit collector application with an audit store
    When I POST a valid audit event to "/events"
    Then the response status code should be 202
    And the response should only contain fields "status" and "eventId"
    And the response should not contain the full stored event

  Scenario: Health check endpoint returns service status
    Given an audit collector application with an audit store
    When I GET "/health"
    Then the response status code should be 200
    And the response should contain "status" with value "healthy"
    And the response should contain "service" with value "audit-collector"

  Scenario: Collector rejects invalid audit event with validation error
    Given an audit collector application with an audit store
    When I POST an invalid audit event to "/events" missing required field "eventType"
    Then the response status code should be 422

  Scenario: Collector returns error when storage fails
    Given an audit collector application with a failing audit store
    When I POST a valid audit event to "/events"
    Then the response status code should be 500
    And the response should contain "detail" with value "Failed to store audit event"

  Scenario: Collector only accepts POST method on events endpoint
    Given an audit collector application with an audit store
    When I GET "/events"
    Then the response status code should be 405

  Scenario: Create collector app with default configuration from environment
    Given the environment variable "AUDIT_DATABASE_URL" is set to "postgresql://user:pass@host:5432/db"
    When I create a collector app using createApp
    Then a FastAPI application should be created
    And the application title should be "ACE Audit Collector"
    And the application version should be "1.0.0"
