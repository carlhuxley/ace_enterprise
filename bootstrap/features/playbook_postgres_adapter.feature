Feature: PostgreSQL-backed Playbook Adapter
  As a caller of the playbook storage interface
  I want to create, retrieve, and search playbooks and bullets
  So that I can manage domain knowledge with persistent, searchable storage

  Scenario: Creating a new playbook returns an empty structure with default sections
    Given a playbook creation request with domain "customer_support" and base_model "gpt-4"
    When I create the playbook
    Then a new playbook is returned with a unique playbook_id
    And its version is "0.1.0"
    And its metadata shows domain "customer_support", base_model "gpt-4", total_tokens 0, and total_bullets 0
    And it contains the sections "strategies_and_hard_rules", "code_snippets", "troubleshooting", and "domain_knowledge", each empty

  Scenario: Retrieving a playbook that does not exist returns nothing
    Given no playbook exists with id "playbook-unknown-123"
    When I request the playbook with id "playbook-unknown-123"
    Then the result is empty

  Scenario: Retrieving an existing playbook returns its bullets organized by section
    Given a playbook "playbook-abc" exists with a bullet "Always validate input" in section "strategies_and_hard_rules"
    When I request the playbook with id "playbook-abc"
    Then the returned playbook's "strategies_and_hard_rules" section contains a bullet with content "Always validate input"

  Scenario: Adding a bullet to an existing playbook succeeds
    Given a playbook "playbook-abc" exists
    When I add a bullet with content "Use retries for flaky network calls" to section "troubleshooting" with tags ["networking", "resilience"]
    Then a new bullet is returned with a unique id
    And the bullet's content is "Use retries for flaky network calls"
    And the bullet's section is "troubleshooting"
    And the bullet's helpful_count and harmful_count are both 0

  Scenario: Adding a bullet to a non-existent playbook fails
    Given no playbook exists with id "playbook-missing"
    When I attempt to add a bullet with content "Some tip" to section "domain_knowledge" for playbook "playbook-missing"
    Then the operation fails with an error indicating the playbook was not found

  Scenario: Adding a bullet with an invalid section fails
    Given a playbook "playbook-abc" exists
    When I attempt to add a bullet with content "Some tip" to section "invalid_section_name"
    Then the operation fails with an error indicating the section is invalid

  Scenario: Retrieving all bullets from a playbook flattens all sections
    Given a playbook "playbook-abc" has 2 bullets in "code_snippets" and 1 bullet in "troubleshooting"
    When I request all bullets for playbook "playbook-abc"
    Then a list of 3 bullets is returned

  Scenario: Semantic search returns bullets ranked by similarity above the threshold
    Given a playbook "playbook-abc" contains a bullet "Retry failed API calls with exponential backoff"
    When I search within playbook "playbook-abc" for "how to handle API failures" with top_k 5 and similarity_threshold 0.3
    Then a list of matching bullets is returned, each paired with a similarity score of at least 0.3
    And the results are ordered by decreasing similarity

  Scenario: Listing playbooks returns all stored playbook ids
    Given playbooks "playbook-abc" and "playbook-xyz" have been created
    When I list all playbooks
    Then the returned list contains "playbook-abc" and "playbook-xyz"