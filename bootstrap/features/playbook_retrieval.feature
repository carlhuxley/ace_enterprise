Feature: Fine-Grained Bullet Retrieval
  As a caller of the retrieval engine
  I want to fetch, filter, and rank playbook bullets relevant to a query
  So that I can surface the most useful guidance for a given context

  Scenario: Retrieving bullets ranked by relevance to a query
    Given a retriever configured with top_k 2 and similarity_threshold 0.1
    And a list of bullets including one whose content is "Always validate user input before processing"
    And a list of bullets including one whose content is "Cats are popular pets"
    When I call retrieve with query "validate user input"
    Then the result contains at most 2 (bullet, score) tuples
    And the bullet about "Always validate user input before processing" appears before the bullet about "Cats are popular pets"

  Scenario: Query with no embeddings and no keyword overlap returns no results
    Given a retriever configured with similarity_threshold 0.5
    And a bullet with content "Deploy using blue-green strategy" and no embedding
    When I call retrieve with query "unrelated topic xyz" and no query_embedding
    Then the result is an empty list

  Scenario: Filtering retrieval by section
    Given a retriever with default configuration
    And a bullet "A" with section "testing" and content matching the query
    And a bullet "B" with section "deployment" and content matching the query
    When I call retrieve with query matching both bullets and filter_section "testing"
    Then the result contains only bullet "A"

  Scenario: Filtering retrieval by minimum confidence score
    Given a retriever with default configuration
    And a bullet "A" with confidence_score 0.9 and content matching the query
    And a bullet "B" with confidence_score 0.2 and content matching the query
    When I call retrieve with query matching both bullets and min_confidence 0.5
    Then the result contains only bullet "A"

  Scenario: Filtering retrieval by domain applicability
    Given a retriever with default configuration
    And a bullet "A" applicable to domains ["finance"] with content matching the query
    And a bullet "B" applicable to domains ["healthcare"] with content matching the query
    When I call retrieve with query matching both bullets and domain "finance"
    Then the result contains only bullet "A"

  Scenario: Retrieving from an empty bullet list returns no results
    Given a retriever with default configuration
    When I call retrieve with query "anything" and an empty list of bullets
    Then the result is an empty list

  Scenario: Cross-model retrieval down-weights secondary playbook matches
    Given a retriever configured with similarity_threshold 0.1
    And a primary playbook "pb-primary" containing a bullet whose content matches the query
    And a secondary playbook "pb-secondary" containing a bullet whose content equally matches the query
    When I call retrieve_cross_model with the query, primary_playbook_id "pb-primary", and secondary_weight 0.5
    Then each result tuple includes a source playbook id
    And the bullet sourced from "pb-primary" has a higher score than the equally-matching bullet sourced from "pb-secondary"

  Scenario: Retrieving bullets by explicit IDs preserves requested order and skips missing IDs
    Given a list of bullets with ids "b1", "b2", "b3"
    When I call retrieve_by_ids with ids ["b3", "b1", "does-not-exist"]
    Then the result is the bullets for "b3" then "b1", in that order
    And no error is raised for the missing id "does-not-exist"

  Scenario: Computing section distribution of retrieved results
    Given a retrieved list containing two bullets from section "testing" and one bullet from section "deployment"
    When I call get_section_distribution on the retrieved list
    Then the result is {"testing": 2, "deployment": 1}

  Scenario: Filtering bullets by required and excluded tags
    Given a bullet "A" tagged ["security", "backend"]
    And a bullet "B" tagged ["frontend"]
    And a bullet "C" tagged ["security", "deprecated"]
    When I call filter_by_tags with required_tags ["security"] and excluded_tags ["deprecated"]
    Then the result contains only bullet "A"

  Scenario: Reranking by recency boosts more recently created bullets
    Given a scored result list containing an older bullet "A" with score 0.5
    And a newer bullet "B" with score 0.45
    When I call rerank_by_recency with recency_weight 0.5
    Then bullet "B" may be ranked above bullet "A" due to the recency boost