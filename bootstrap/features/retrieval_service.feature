Feature: Institutional Knowledge Service
  As a code generation consumer
  I want to retrieve institutional knowledge guidance for a query
  So that I can apply confirmed patterns and clarify uncertain ones

  Scenario: No playbook manager configured returns an empty response
    Given an InstitutionalKnowledgeService created with no playbook manager
    When I call get_guidance with query "handle database connection timeout"
    Then the response query is "handle database connection timeout"
    And the response has no results

  Scenario: No bullets found for the given playbook returns an empty response
    Given an InstitutionalKnowledgeService with a playbook manager containing no bullets for playbook "backend"
    When I call get_guidance with query "handle retries" and playbook_id "backend"
    Then the response query is "handle retries"
    And the response has no results

  Scenario: Guidance for a TDD test cycle scopes the query and domain
    Given an InstitutionalKnowledgeService with a playbook manager containing matching bullets in domain "tdd"
    When I call get_guidance_for_tdd with test_name "test_retry_logic" and implementation_context "retry on timeout"
    Then the underlying query sent for retrieval is "writing test test_retry_logic: retry on timeout"
    And the retrieval is scoped to domain "tdd"

  Scenario: Guidance for implementing a feature wraps the description in a query
    Given an InstitutionalKnowledgeService with a playbook manager containing matching bullets
    When I call get_guidance_for_implementation with feature_description "add caching layer"
    Then the underlying query sent for retrieval is "implementing: add caching layer"

  Scenario: Getting anti-patterns scopes the query and domain
    Given an InstitutionalKnowledgeService with a playbook manager containing matching bullets in domain "anti-patterns"
    When I call get_anti_patterns with context_description "database connections"
    Then the underlying query sent for retrieval is "anti-patterns avoid database connections"
    And the retrieval is scoped to domain "anti-patterns"

  Scenario: Formatting a response with confirmed patterns lists them for prompt injection
    Given a KnowledgeResponse with apply patterns containing content "Use connection pooling"
    When I call format_guidance on the response with include_ask_first false
    Then the formatted text contains the heading "**Confirmed patterns (safe to apply):**"
    And the formatted text contains "- Use connection pooling"

  Scenario: Formatting a response with only uncertain patterns and include_ask_first false yields no results message
    Given a KnowledgeResponse with only ask_first patterns and no apply patterns
    When I call format_guidance on the response with include_ask_first false
    Then the formatted text is "No relevant patterns found."

  Scenario: Formatting a response with uncertain patterns and include_ask_first true lists context gaps
    Given a KnowledgeResponse with an ask_first pattern with content "Use exponential backoff" and context gap description "team_id not specified"
    When I call format_guidance on the response with include_ask_first true
    Then the formatted text contains "**Patterns that may apply (verify context):**"
    And the formatted text contains "- Use exponential backoff"
    And the formatted text contains "*Note: team_id not specified*"

  Scenario: The knowledge service singleton returns the same instance across calls
    Given no prior call to get_knowledge_service in this process
    When I call get_knowledge_service twice without force_new
    Then both calls return the same InstitutionalKnowledgeService instance

  Scenario: Forcing a new instance replaces the singleton
    Given an existing singleton instance from a prior call to get_knowledge_service
    When I call get_knowledge_service with force_new true
    Then the returned instance is different from the prior singleton instance