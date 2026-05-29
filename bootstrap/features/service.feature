Feature: Institutional Knowledge Service
  Retrieves and formats relevant playbook guidance for a given query

  Scenario: Get guidance with no playbook manager returns empty response
    Given a knowledge service with no playbook manager configured
    When guidance is requested for query "handle database timeout"
    Then the response has no results
    And the response query is "handle database timeout"

  Scenario: Get guidance for TDD returns a response
    Given a knowledge service with a playbook manager containing bullets
    When TDD guidance is requested with test_name "test_user_login" and context "authentication flow"
    Then a non-empty response is returned

  Scenario: Get anti-patterns returns a response
    Given a knowledge service with a playbook manager
    When anti-patterns are requested for context "database migrations"
    Then the response query contains "database migrations"

  Scenario: Format guidance with apply patterns produces non-empty text
    Given a knowledge response with 2 apply-type patterns
    When the guidance is formatted
    Then the result is a non-empty string

  Scenario: Format guidance with no results returns a fallback string
    Given a knowledge response with no results
    When the guidance is formatted
    Then the result is a non-empty string
