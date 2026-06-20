Feature: Context Graph Retriever
  As a knowledge retrieval system
  I want to retrieve, rank, and reason about knowledge bullets
  So that I can provide context-aware recommendations with actionable verdicts

  Scenario: Retrieve with no candidates returns empty response
    Given a ContextGraphRetriever with default settings
    And an empty list of bullets
    When I retrieve with query "handle auth timeout"
    Then the response has 0 total candidates
    And the response has 0 apply bullets
    And the response has 0 askFirst bullets
    And the response retrievalTimeMs is greater than 0

  Scenario: Retrieve with high context match produces APPLY verdict
    Given a ContextGraphRetriever with contextWeight 0.4
    And a bullet with content "Use retry logic for auth timeouts" with teamId "payments"
    And a RetrievalContext with teamId "payments"
    When I retrieve with query "handle auth timeout" and the context
    Then the response has at least 1 apply bullet
    And the first apply bullet has verdict "APPLY"
    And the first apply bullet has reasoning "Context matches well"
    And the first apply bullet has 0 context gaps with severity greater than 0.3

  Scenario: Retrieve with low context score produces ASK_FIRST verdict
    Given a ContextGraphRetriever with minContextScore 0.3
    And a bullet with content "Use retry logic" with teamId "payments" and techStack "java"
    And a RetrievalContext with teamId "platform" and techStack "python"
    When I retrieve with query "retry logic" and the context
    Then the response has 0 apply bullets
    And the response has at least 1 askFirst bullet
    And the first askFirst bullet has verdict "ASK_FIRST"
    And the first askFirst bullet contextScore is less than 0.3

  Scenario: Retrieve with very low context score produces SKIP verdict
    Given a ContextGraphRetriever with skipThreshold 0.15
    And a bullet with content "Legacy pattern" with teamId "old-team" and projectId "deprecated"
    And a RetrievalContext with teamId "new-team" and projectId "active"
    When I retrieve with query "legacy pattern" and the context
    Then the response has 0 apply bullets
    And the response has 0 askFirst bullets
    And the response totalCandidates is 1

  Scenario: Retrieve with topK limits results
    Given a ContextGraphRetriever with default settings
    And 10 bullets with varying content and context
    When I retrieve with query "test query" and topK 3
    Then the response has at most 3 total results across apply and askFirst
    And the results are ordered by combinedScore descending

  Scenario: Retrieve without context uses default empty context
    Given a ContextGraphRetriever with default settings
    And a bullet with content "Generic pattern"
    When I retrieve with query "generic" without providing context
    Then the response context has no teamId
    And the response context has no projectId
    And the response has at least 1 result

  Scenario: Combined score blends semantic and context scores
    Given a ContextGraphRetriever with contextWeight 0.4
    And a bullet with semanticScore 0.8 and contextScore 0.6
    When I retrieve the bullet
    Then the ranked bullet combinedScore equals 0.72
    And the combinedScore is calculated as semanticScore * 0.6 + contextScore * 0.4

  Scenario: Explain verdict generates human-readable explanation
    Given a ContextGraphRetriever with default settings
    And a RankedBullet with content "Test pattern", semanticScore 0.85, contextScore 0.70, verdict "APPLY", and 1 context gap
    When I call explainVerdict on the ranked bullet
    Then the explanation contains "Pattern: Test pattern"
    And the explanation contains "Semantic score: 0.85"
    And the explanation contains "Context score: 0.70"
    And the explanation contains "Verdict: APPLY"
    And the explanation contains "Context gaps:"

  Scenario: Retrieve with lineage delegates to regular retrieve
    Given a ContextGraphRetriever with default settings
    And a bullet with content "Current pattern"
    And a RetrievalContext with teamId "test-team"
    When I call retrieveWithLineage with query "pattern", bullets, context, and includeSuperseded False
    Then the response is equivalent to calling retrieve with the same parameters
    And the response has at least 1 result