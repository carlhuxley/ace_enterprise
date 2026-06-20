Feature: Audit Event Collector Service
  As an ACE agent
  I want to submit audit events to the collector
  So that they can be stored in the immutable audit log

  Scenario: Successfully submit a valid audit event
    Given an audit collector application with an audit store
    When I POST a valid audit event to "/events" with fields:
      | field       | value                                      |
      | eventType  | user.login                                 |
      | timestamp   | 2024-01-15T10:30:00Z                       |
      | actor       | user-123                                   |
      | resource    | system                                     |
      | action      | authenticate                               |
      | outcome     | success                                    |
    Then the response status code should be 202
    And the response should contain "status" with value "accepted"
    And the response should contain "event_id"

  Scenario: Health check endpoint returns service status
    Given an audit collector application with an audit store
    When I GET "/health"
    Then the response status code should be 200
    And the response should contain "status" with value "healthy"
    And the response should contain "service" with value "audit-collector"

  Scenario: Submit audit event with all optional metadata
    Given an audit collector application with an audit store
    When I POST a valid audit event to "/events" with fields:
      | field       | value                                      |
      | eventType  | data.access                                |
      | timestamp   | 2024-01-15T14:22:00Z                       |
      | actor       | service-456                                |
      | resource    | database-records                           |
      | action      | read                                       |
      | outcome     | success                                    |
      | metadata    | {"record_count": 42, "query": "SELECT *"}  |
    Then the response status code should be 202
    And the response should contain "status" with value "accepted"
    And the response should contain "event_id"

  Scenario: Fail to submit event when storage fails
    Given an audit collector application with a failing audit store
    When I POST a valid audit event to "/events" with fields:
      | field       | value                    |
      | eventType  | system.error             |
      | timestamp   | 2024-01-15T16:00:00Z     |
      | actor       | admin-789                |
      | resource    | config                   |
      | action      | update                   |
      | outcome     | failure                  |
    Then the response status code should be 500
    And the response should contain "detail" with value "Failed to store audit event"

  Scenario: Submit multiple audit events independently
    Given an audit collector application with an audit store
    When I POST a valid audit event to "/events" with eventType "user.login"
    And I POST a valid audit event to "/events" with eventType "user.logout"
    Then both responses should have status code 202
    And both responses should contain "status" with value "accepted"
    And both responses should contain unique "event_id" values

  Scenario: Collector initializes audit store on startup
    Given an audit store that has not been initialized
    When I create an audit collector application with that store
    Then the audit store tables should be created
    And the application should be ready to accept events