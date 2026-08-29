Feature: Domain-Aware Distillation Router
  As a caller integrating weak and strong models, I want task queries routed to
  domain-specific distillation context or a strong-model fallback, so that I know
  which model to invoke and what system prompt to use.

  Scenario: Query strongly matches a known domain
    Given a router configured with a high-confidence threshold of 0.7
    And the domain "oauth2_authentication" has compatible distillation knowledge available
    When I route the query "Implement OAuth2 refresh token flow"
    And the query matches domain "oauth2_authentication" with confidence 0.85
    Then the routing verdict is "use_distillation"
    And "use_teacher" is False
    And the result includes a non-empty system prompt containing "oauth2_authentication"
    And the result includes at least one distillation bullet

  Scenario: Query has low confidence match across all domains
    Given a router configured with a low-confidence threshold of 0.4
    When I route the query "Compose a haiku about databases"
    And the best matching domain has confidence 0.15
    Then the routing verdict is "use_teacher"
    And "use_teacher" is True
    And the result has no system prompt
    And the result has no distillation bullets

  Scenario: Query has moderate confidence and should be confirmed with the user
    Given a router configured with thresholds high=0.7 and low=0.4
    When I route the query "Optimize a database query"
    And the best matching domain has confidence 0.55
    Then the routing verdict is "ask_first"

  Scenario: No domains are registered yet
    Given a router whose playbook manager has no domains configured
    When I route the query "Set up CI pipeline"
    Then the routing verdict is "use_teacher"
    And the result's domain is None

  Scenario: Student model provenance filters out incompatible bullets, leaving none usable
    Given a router with distillation knowledge for domain "sql_optimization" authored entirely by a proprietary OpenAI model
    And I route as student model "claude-3-sonnet" from provider "anthropic"
    When I route the query "Optimize a database query"
    And the query matches domain "sql_optimization" with confidence 0.9
    Then the routing verdict is "use_teacher"
    And the recommended teacher supplier is "anthropic"

  Scenario: Student and teacher share the same supplier so knowledge is not filtered
    Given a router with distillation knowledge for domain "gemini_prompting" authored by model "gemini-pro" from provider "google"
    And I route as student model "gemma2" from provider "google"
    When I route the query "Write a Gemini system prompt"
    And the query matches domain "gemini_prompting" with confidence 0.9
    Then the routing verdict is "use_distillation"
    And no bullets are filtered out due to provenance

  Scenario: Caller routes directly to a known domain, bypassing query classification
    Given a router with domain "kubernetes_deployment" available
    When I call route_to_domain with domain "kubernetes_deployment"
    Then the routing verdict is "use_distillation"
    And the confidence is 1.0
    And the result's domain is "kubernetes_deployment"

  Scenario: Caller routes directly to an unknown domain
    Given a router without domain "quantum_computing" available
    When I call route_to_domain with domain "quantum_computing"
    Then the routing verdict is "use_teacher"
    And the result's domain is None

  Scenario: Listing all available domains
    Given a router with domains "oauth2_authentication", "sql_optimization", and "kubernetes_deployment" registered
    When I call get_all_domains
    Then the returned list contains "oauth2_authentication", "sql_optimization", and "kubernetes_deployment"