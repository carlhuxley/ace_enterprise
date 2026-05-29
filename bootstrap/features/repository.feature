Feature: Playbook Repository
  Stores and retrieves playbooks and bullets with optional vector similarity search

  Scenario: Create a playbook and retrieve it by ID
    Given a repository instance
    When a playbook is created with playbook_id "pb-001" and domain "sales"
    And the playbook is retrieved by playbook_id "pb-001"
    Then the returned playbook has playbook_id "pb-001"
    And the returned playbook has domain "sales"

  Scenario: Retrieve a non-existent playbook returns nothing
    Given a repository instance
    When the playbook with playbook_id "pb-missing" is retrieved
    Then no playbook is returned

  Scenario: Get-or-create returns existing playbook unchanged
    Given a repository instance with a playbook "pb-existing" at domain "sales"
    When get_or_create is called with playbook_id "pb-existing" and domain "marketing"
    Then the returned playbook still has domain "sales"

  Scenario: Add a bullet to a playbook and retrieve it
    Given a repository instance with playbook "pb-002"
    When a bullet is added with content "Close the deal" and section "tactics"
    And bullets are retrieved from playbook "pb-002"
    Then the list contains 1 bullet
    And the bullet content is "Close the deal"

  Scenario: Similarity search returns results sorted by relevance
    Given a repository instance with playbook "pb-003" containing 3 bullets with embeddings
    When similarity search is performed with a query embedding and top_k 2
    Then at most 2 results are returned
    And the results are sorted by score in descending order

  Scenario: Get repository statistics includes counts
    Given a repository instance with 2 playbooks and 5 bullets total
    When repository stats are requested
    Then the stats include a total_playbooks count
    And the stats include a total_bullets count
