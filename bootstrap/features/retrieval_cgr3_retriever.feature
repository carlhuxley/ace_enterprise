Feature: CGR³ Context Graph Retriever
  As a caller of the knowledge retrieval pipeline
  I want to retrieve, rank, and reason about candidate patterns
  So that I only receive patterns that are safe to apply or that need clarification

  Scenario: No candidates found for a query
    Given a set of bullets that has no semantic match for the query "handle auth timeout"
    When I call retrieve with that query and bullet set
    Then the response has zero total_candidates
    And the response has an empty apply list
    And the response has an empty ask_first list

  Scenario: A well-matched pattern is categorized as APPLY
    Given a bullet whose content and context align closely with team "payments" and tech stack {"python": "3.11", "framework": "fastapi"}
    And a query "handle auth timeout" that semantically matches this bullet
    When I call retrieve with this query, bullet, and a context for team "payments" with tech stack {"python": "3.11", "framework": "fastapi"}
    Then the response's apply list contains that bullet
    And the response's ask_first list does not contain that bullet

  Scenario: A partially-matched pattern is categorized as ASK_FIRST
    Given a bullet that semantically matches the query but has some context mismatches with the caller's team or tech stack
    When I call retrieve with this query, bullet, and the mismatched context
    Then the response's ask_first list contains that bullet
    And the response's apply list does not contain that bullet

  Scenario: A poorly-matched pattern is excluded from the response entirely
    Given a bullet that semantically matches the query but has severe context mismatches
    When I call retrieve with this query, bullet, and the mismatched context
    Then the response's apply list does not contain that bullet
    And the response's ask_first list does not contain that bullet
    And the response's total_candidates still counts that bullet as a retrieved candidate

  Scenario: Limiting results with top_k
    Given five bullets that all semantically match the query "improve retry logic"
    When I call retrieve with top_k set to 2
    Then the combined number of bullets in the apply and ask_first lists is at most 2

  Scenario: Retrieving without an explicit context uses default context
    Given a bullet set with at least one semantic match for the query "reduce latency"
    When I call retrieve with that query and bullet set and no context argument
    Then the response is returned without error
    And the response's context reflects a default, unconstrained context

  Scenario: Retrieving with lineage returns the same shape as a normal retrieve
    Given a bullet set with at least one semantic match for the query "handle auth timeout"
    When I call retrieve_with_lineage with that query and bullet set
    Then the response contains apply and ask_first lists consistent with calling retrieve directly with the same inputs

  Scenario: Explaining a ranked bullet's verdict produces a human-readable summary
    Given a ranked bullet with semantic_score 0.80, context_score 0.50, combined_score 0.62, verdict "apply", and one context gap describing a mismatched tech stack
    When I call explain_verdict with that ranked bullet
    Then the returned string includes the bullet's content
    And the returned string includes the semantic, context, and combined scores
    And the returned string includes the verdict in uppercase
    And the returned string includes a description of the context gap