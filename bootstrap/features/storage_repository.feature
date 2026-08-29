Feature: PostgreSQL Playbook Repository

  Scenario: Creating a new playbook
    Given no playbook exists with ID "incident-response-v1"
    When I create a playbook with ID "incident-response-v1", version "1.0", domain "sre", and base model "gpt-4"
    Then a playbook with ID "incident-response-v1" is returned
    And the playbook has version "1.0", domain "sre", and base model "gpt-4"

  Scenario: Getting or creating a playbook that already exists
    Given a playbook with ID "incident-response-v1" already exists
    When I call get-or-create with ID "incident-response-v1", version "2.0", domain "sre", and base model "gpt-4"
    Then the existing playbook is returned unchanged
    And no duplicate playbook with ID "incident-response-v1" is created

  Scenario: Adding a bullet to a nonexistent playbook fails
    Given no playbook exists with ID "ghost-playbook"
    When I add a bullet with ID "b1", content "Always check logs first", section "triage", and tags ["logs", "triage"] to playbook "ghost-playbook"
    Then a "Playbook not found: ghost-playbook" error is raised

  Scenario: Adding a bullet without an embedding generates one automatically
    Given a playbook with ID "incident-response-v1" exists
    When I add a bullet with ID "b1", content "Always check logs first", section "triage", and tags ["logs", "triage"] without providing an embedding
    Then the bullet is stored with a generated embedding
    And the playbook's total bullet count increases by 1

  Scenario: Retrieving bullets filtered by section and tags
    Given a playbook with ID "incident-response-v1" has bullets in sections "triage" and "mitigation"
    When I request bullets from playbook "incident-response-v1" filtered by section "triage" and tags ["logs"]
    Then only bullets matching section "triage" and containing at least one of the tags ["logs"] are returned

  Scenario: Semantic similarity search returns results ordered by relevance
    Given a playbook "incident-response-v1" contains bullets with embeddings
    When I perform a similarity search with a query embedding, top_k of 5, and similarity_threshold of 0.5
    Then up to 5 bullets are returned as (bullet, similarity_score) pairs
    And every returned similarity_score is at least 0.5
    And results are ordered from most to least similar

  Scenario: Similarity search rejects an invalid distance metric
    Given a query embedding is available
    When I perform a similarity search with distance_metric "manhattan"
    Then a "Invalid distance metric: manhattan" error is raised

  Scenario: Bulk adding bullets to a playbook
    Given a playbook with ID "incident-response-v1" exists
    When I bulk add 3 bullets, each missing an embedding but having content
    Then 3 bullets are added to the playbook
    And each added bullet has a generated embedding
    And the playbook's total bullet count reflects all added bullets