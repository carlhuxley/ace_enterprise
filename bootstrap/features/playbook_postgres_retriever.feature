Feature: PostgreSQL-backed Bullet Retriever

  As a caller of the retrieval system
  I want to fetch relevant bullets from a playbook using semantic search
  So that I receive ranked, filtered results without loading all bullets into memory

  Scenario: Retrieve bullets for a simple query returns ranked results
    Given a retriever configured with a default top_k of 5
    When I call retrieve with query "how to handle timeout errors"
    Then I receive a list of (bullet, score) tuples
    And the list contains at most 5 entries

  Scenario: Bullets below the minimum confidence threshold are excluded
    Given the underlying search would return a bullet with confidence_score 0.3
    When I call retrieve with query "database connection pooling" and min_confidence 0.5
    Then that bullet is not present in the returned results

  Scenario: Filtering by section only returns bullets from that section
    Given the underlying search would return bullets from sections "setup" and "troubleshooting"
    When I call retrieve with query "environment configuration" and filter_section "setup"
    Then only bullets with section "setup" are present in the returned results

  Scenario: Filtering by domain excludes bullets not applicable to that domain
    Given a bullet has applicable_domains ["finance", "legal"]
    When I call retrieve with query "audit process" and domain "healthcare"
    Then that bullet is not present in the returned results

  Scenario: Filtering by project_id excludes bullets not applicable to that project
    Given a bullet has project_ids ["proj-123"]
    When I call retrieve with query "deployment steps" and project_id "proj-999"
    Then that bullet is not present in the returned results

  Scenario: Filtering by minimum helpful ratio excludes low-ratio bullets
    Given a bullet has helpful_count 1 and harmful_count 9
    When I call retrieve with query "rollback procedure" and min_helpful_ratio 0.7
    Then that bullet is not present in the returned results

  Scenario: retrieve_from_bullets delegates to database-backed retrieval
    Given a list of pre-filtered bullets and a query embedding
    When I call retrieve_from_bullets with query "caching strategy" and filter_section "performance"
    Then I receive a list of (bullet, score) tuples equivalent to calling retrieve with the same query and filter_section

  Scenario: Cross-model retrieval down-weights bullets from secondary playbooks
    Given a bullet originates from playbook "playbook-B" with similarity score 0.8
    And the primary playbook is "playbook-A"
    And secondary_weight is 0.5
    When I call retrieve_cross_model with query "incident response" and primary_playbook_id "playbook-A"
    Then the returned tuple for that bullet has score 0.4 and source playbook "playbook-B"
    And results are sorted by score in descending order