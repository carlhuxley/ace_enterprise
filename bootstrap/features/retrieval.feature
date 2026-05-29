Feature: Bullet Retrieval
  Retrieves relevant playbook bullets by semantic similarity with optional filters

  Scenario: Retrieve returns results sorted by score descending
    Given a retriever with 5 bullets and a query embedding
    When retrieve is called with similarity_threshold 0.0 and top_k 3
    Then at most 3 results are returned
    And each result has a score of 0.0 or higher
    And results are ordered by score from highest to lowest

  Scenario: Retrieve filtered by section returns only matching bullets
    Given a retriever with bullets in sections "setup" and "deployment"
    When retrieve is called with filter_section "setup"
    Then all returned bullets have section "setup"

  Scenario: Retrieve filtered by confidence excludes low-confidence bullets
    Given a retriever with bullets at confidence 0.9, 0.6, and 0.3
    When retrieve is called with min_confidence 0.5
    Then only bullets with confidence 0.5 or higher are returned

  Scenario: Retrieve by IDs returns exactly the requested bullets
    Given a retriever with bullets "bullet-1", "bullet-2", "bullet-3"
    When retrieve_by_ids is called with ["bullet-1", "bullet-3"]
    Then exactly 2 bullets are returned
    And both "bullet-1" and "bullet-3" are present

  Scenario: Empty bullet list returns empty results
    Given a retriever with no bullets
    When retrieve is called
    Then an empty list is returned

  Scenario: Cross-model retrieval applies secondary weight to non-primary bullets
    Given a retriever with 3 primary bullets and 3 secondary bullets
    When retrieve_cross_model is called with secondary_weight 0.5
    Then secondary bullet scores are reduced relative to primary scores
    And results are sorted by weighted score descending
