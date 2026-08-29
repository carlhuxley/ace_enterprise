Feature: CGR³ retrieval schemas
  As a caller of the institutional knowledge retrieval system
  I want structured context, ranking, and response objects
  So that I can distinguish safe-to-apply patterns from those needing clarification

  Scenario: A knowledge response with no candidates reports no results
    Given a KnowledgeResponse with an empty "apply" list and an empty "ask_first" list
    When I check the "has_results" property
    Then it should be False

  Scenario: A knowledge response with an applicable pattern reports results
    Given a KnowledgeResponse whose "apply" list contains one RankedBullet
    And its "ask_first" list is empty
    When I check the "has_results" property
    Then it should be True

  Scenario: A knowledge response with only ask-first patterns still reports results
    Given a KnowledgeResponse whose "apply" list is empty
    And its "ask_first" list contains one RankedBullet
    When I check the "has_results" property
    Then it should be True

  Scenario: Generating a clarifying question from a short bullet with a single context gap
    Given a RankedBullet in "ask_first" whose bullet content is "Use retries for flaky network calls"
    And it has one ContextGap with description "team_id not provided"
    When I read the "questions" property of the KnowledgeResponse
    Then it should contain "Pattern 'Use retries for flaky network calls' may apply, but: team_id not provided"

  Scenario: Generating a clarifying question truncates long bullet content
    Given a RankedBullet in "ask_first" whose bullet content is "This is a very long pattern description that exceeds fifty characters in total length"
    And it has one ContextGap with description "tech_stack mismatch"
    When I read the "questions" property of the KnowledgeResponse
    Then the question should start with "Pattern 'This is a very long pattern description that ex...' may apply, but: tech_stack mismatch"

  Scenario: Generating a clarifying question with multiple context gaps
    Given a RankedBullet in "ask_first" whose bullet content is "Enable circuit breaker"
    And it has two ContextGaps with descriptions "team_id missing" and "domain mismatch"
    When I read the "questions" property of the KnowledgeResponse
    Then it should contain "Pattern 'Enable circuit breaker' may apply, but: team_id missing, domain mismatch"

  Scenario: A retrieval context defaults to no identifying information
    Given a RetrievalContext created with no arguments
    When I inspect its fields
    Then "team_id", "user_id", "project_id", "project_path", "domain", and "session_id" should all be None
    And "tech_stack" should be an empty dictionary

  Scenario: A ranked bullet defaults to the APPLY verdict when none is specified
    Given a RankedBullet created with semantic_score 0.9, context_score 0.8, and combined_score 0.85
    And no verdict is explicitly provided
    When I inspect its "verdict" field
    Then it should equal "apply"