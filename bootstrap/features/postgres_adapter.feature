Feature: PostgreSQL Playbook Adapter
  As a user of the playbook system
  I want to manage playbooks and bullets using PostgreSQL storage
  So that I can persist and search playbook data

  Scenario: Create a new playbook
    Given no playbooks exist in the system
    When I create a playbook with domain "python-testing" and baseModel "gpt-4"
    Then the playbook should have a unique playbookId
    And the playbook version should be "0.1.0"
    And the playbook metadata domain should be "python-testing"
    And the playbook metadata baseModel should be "gpt-4"
    And the playbook metadata totalTokens should be 0
    And the playbook metadata totalBullets should be 0
    And the playbook should have 4 empty sections: "strategies_and_hard_rules", "code_snippets", "troubleshooting", "domain_knowledge"

  Scenario: Retrieve an existing playbook
    Given a playbook exists with id "pb-12345" and domain "javascript"
    When I get the playbook with id "pb-12345"
    Then the playbook should be returned
    And the playbookId should be "pb-12345"
    And the metadata domain should be "javascript"

  Scenario: Retrieve a non-existent playbook
    Given no playbook exists with id "pb-nonexistent"
    When I get the playbook with id "pb-nonexistent"
    Then None should be returned

  Scenario: Add a bullet to a playbook
    Given a playbook exists with id "pb-67890"
    When I add a bullet with content "Always use type hints" and section "strategies_and_hard_rules" to playbook "pb-67890"
    Then the bullet should be created with a unique id starting with "ctx-"
    And the bullet content should be "Always use type hints"
    And the bullet section should be "strategies_and_hard_rules"
    And the bullet helpfulCount should be 0
    And the bullet harmfulCount should be 0
    And the bullet should have an embedding vector

  Scenario: Add a bullet to a non-existent playbook
    Given no playbook exists with id "pb-missing"
    When I attempt to add a bullet to playbook "pb-missing"
    Then a ValueError should be raised with message "Playbook pb-missing not found"

  Scenario: Add a bullet with an invalid section
    Given a playbook exists with id "pb-11111"
    When I attempt to add a bullet with section "invalid_section" to playbook "pb-11111"
    Then a ValueError should be raised with message "Invalid section: invalid_section"

  Scenario: Get all bullets from a playbook
    Given a playbook exists with id "pb-22222"
    And the playbook has 2 bullets in section "strategies_and_hard_rules"
    And the playbook has 1 bullet in section "code_snippets"
    When I get all bullets from playbook "pb-22222"
    Then 3 bullets should be returned

  Scenario: Get all bullets from an empty playbook
    Given a playbook exists with id "pb-33333" with no bullets
    When I get all bullets from playbook "pb-33333"
    Then an empty list should be returned

  Scenario: Semantic search across all playbooks
    Given multiple playbooks exist with various bullets
    And a bullet exists with content "Use pytest fixtures for test setup"
    When I perform a semantic search with query "testing best practices" with topK 5 and similarityThreshold 0.3
    Then a list of bullet and similarity score tuples should be returned
    And each similarity score should be greater than or equal to 0.3
    And at most 5 results should be returned

  Scenario: Semantic search within a specific playbook
    Given a playbook exists with id "pb-44444"
    And the playbook has bullets about Python testing
    When I perform a semantic search with query "unit tests" for playbookId "pb-44444" with topK 3
    Then only bullets from playbook "pb-44444" should be returned
    And at most 3 results should be returned

  Scenario: List all playbook IDs
    Given 3 playbooks exist with ids "pb-aaa", "pb-bbb", "pb-ccc"
    When I list all playbooks
    Then a list containing "pb-aaa", "pb-bbb", "pb-ccc" should be returned