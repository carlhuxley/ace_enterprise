Feature: ACE Enterprise API application endpoints
  As an external client of the ACE Enterprise API
  I want to query system status and API information
  So that I can monitor the service and discover basic metadata

  Scenario: Health check reports service status
    When I send a GET request to "/health"
    Then the response status code is 200
    And the response body contains a "status" field equal to "healthy"
    And the response body contains a "version" field
    And the response body contains an "environment" field
    And the response body contains a "llm_provider" field

  Scenario: Root endpoint returns API metadata
    When I send a GET request to "/"
    Then the response status code is 200
    And the response body contains a "name" field
    And the response body contains a "version" field
    And the response body contains a "description" field
    And the response body contains a "docs" field

  Scenario: Root endpoint reports docs location in development environment
    Given the application is running with development mode enabled
    When I send a GET request to "/"
    Then the response body's "docs" field is equal to "/docs"

  Scenario: Root endpoint reports docs disabled in production environment
    Given the application is running with development mode disabled
    When I send a GET request to "/"
    Then the response body's "docs" field is equal to "Documentation disabled in production"

  Scenario: Interactive API docs are available in development environment
    Given the application is running with development mode enabled
    When I send a GET request to "/docs"
    Then the response status code is 200

  Scenario: Interactive API docs are unavailable in production environment
    Given the application is running with development mode disabled
    When I send a GET request to "/docs"
    Then the response status code is 404

  Scenario: Prometheus metrics endpoint is exposed when enabled
    Given Prometheus metrics are enabled in the application configuration
    When I send a GET request to "/metrics"
    Then the response status code is 200

  Scenario: Cross-origin requests are permitted from configured origins
    Given the application is configured to allow cross-origin requests from "https://dashboard.example.com"
    When I send an OPTIONS request to "/health" with an "Origin" header of "https://dashboard.example.com"
    Then the response includes an "Access-Control-Allow-Origin" header equal to "https://dashboard.example.com"