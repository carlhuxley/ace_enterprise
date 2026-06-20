Feature: ACE Enterprise API
  As an API client
  I want to interact with the ACE Enterprise application
  So that I can check system status and access API information

  Scenario: Check application health status
    Given the ACE Enterprise application is running
    When I send a GET request to "/health"
    Then the response status code is 200
    And the response contains a JSON object with field "status" equal to "healthy"
    And the response contains a JSON object with field "version"
    And the response contains a JSON object with field "environment"
    And the response contains a JSON object with field "llm_provider"

  Scenario: Access root endpoint for API information
    Given the ACE Enterprise application is running
    When I send a GET request to "/"
    Then the response status code is 200
    And the response contains a JSON object with field "name"
    And the response contains a JSON object with field "version"
    And the response contains a JSON object with field "description"
    And the response contains a JSON object with field "docs"

  Scenario: Access API documentation in development environment
    Given the application is configured with "is_development" set to true
    And the ACE Enterprise application is running
    When I send a GET request to "/docs"
    Then the response status code is 200

  Scenario: Access API documentation in production environment
    Given the application is configured with "is_development" set to false
    And the ACE Enterprise application is running
    When I send a GET request to "/docs"
    Then the response status code is 404

  Scenario: Access Prometheus metrics when enabled
    Given the application is configured with "enable_prometheus_metrics" set to true
    And the ACE Enterprise application is running
    When I send a GET request to "/metrics"
    Then the response status code is 200

  Scenario: Prometheus metrics endpoint not available when disabled
    Given the application is configured with "enable_prometheus_metrics" set to false
    And the ACE Enterprise application is running
    When I send a GET request to "/metrics"
    Then the response status code is 404

  Scenario: CORS headers are present in responses
    Given the ACE Enterprise application is running
    When I send a GET request to "/health" with origin header "http://example.com"
    Then the response includes CORS headers