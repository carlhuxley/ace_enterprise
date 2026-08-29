Feature: API key authentication for audit services

  Scenario: Server has no API key configured
    Given the server has no AUDIT_API_KEY environment variable set
    When a client sends a request to a protected endpoint with header "X-API-Key: any-value"
    Then the response status is 503
    And the response detail indicates the server refuses to run unauthenticated

  Scenario: Server has no API key configured and client sends no key
    Given the server has no AUDIT_API_KEY environment variable set
    When a client sends a request to a protected endpoint with no "X-API-Key" header
    Then the response status is 503

  Scenario: Request with missing API key is rejected
    Given the server has AUDIT_API_KEY set to "correct-secret-123"
    When a client sends a request to a protected endpoint with no "X-API-Key" header
    Then the response status is 401
    And the response detail is "Invalid or missing API key"

  Scenario: Request with an incorrect API key is rejected
    Given the server has AUDIT_API_KEY set to "correct-secret-123"
    When a client sends a request to a protected endpoint with header "X-API-Key: wrong-secret-999"
    Then the response status is 401
    And the response detail is "Invalid or missing API key"

  Scenario: Request with an empty API key is rejected
    Given the server has AUDIT_API_KEY set to "correct-secret-123"
    When a client sends a request to a protected endpoint with header "X-API-Key: "
    Then the response status is 401

  Scenario: Request with the correct API key is accepted
    Given the server has AUDIT_API_KEY set to "correct-secret-123"
    When a client sends a request to a protected endpoint with header "X-API-Key: correct-secret-123"
    Then the request is allowed to proceed to the endpoint handler

  Scenario: API key comparison is case-sensitive
    Given the server has AUDIT_API_KEY set to "correct-secret-123"
    When a client sends a request to a protected endpoint with header "X-API-Key: CORRECT-SECRET-123"
    Then the response status is 401