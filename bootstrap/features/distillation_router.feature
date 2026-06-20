Feature: Distillation Router

  Scenario: Route query to high-confidence domain
    Given a playbook manager with domain "web_security" containing 15 bullets
    And the domain centroid has high similarity to query "Implement OAuth2 refresh token flow"
    And the similarity score is 0.85
    When I route the query "Implement OAuth2 refresh token flow"
    Then the verdict should be "use_distillation"
    And the domain should be "web_security"
    And the confidence should be 0.85
    And the system prompt should contain "Domain Knowledge: web_security"
    And the distillation bullets count should be greater than 0

  Scenario: Route query to low-confidence domain triggers teacher fallback
    Given a playbook manager with domain "database_optimization" containing 10 bullets
    And the domain centroid has low similarity to query "Build a quantum computer"
    And the similarity score is 0.25
    When I route the query "Build a quantum computer"
    Then the verdict should be "use_teacher"
    And the domain should be None
    And the confidence should be 0.0
    And the system prompt should be None
    And the useTeacher flag should be True

  Scenario: Route query with medium confidence triggers ask-first verdict
    Given a playbook manager with domain "api_design" containing 12 bullets
    And the domain centroid has medium similarity to query "Design REST endpoints"
    And the similarity score is 0.55
    When I route the query "Design REST endpoints"
    Then the verdict should be "ask_first"
    And the domain should be "api_design"
    And the confidence should be 0.55

  Scenario: Route directly to known domain bypasses classification
    Given a playbook manager with domain "kubernetes" containing 20 bullets
    When I route directly to domain "kubernetes" with query "Scale deployment"
    Then the verdict should be "use_distillation"
    And the domain should be "kubernetes"
    And the confidence should be 1.0
    And the system prompt should contain "Domain Knowledge: kubernetes"

  Scenario: Filter bullets by provenance for cross-supplier proprietary
    Given a playbook manager with domain "coding" containing 25 bullets
    And 10 bullets are from "openai" with "proprietary" license
    And 15 bullets are from "meta" with "open_source" license
    And allowCrossSupplierProprietary is False
    When I route the query "Write Python function" with student model "claude-3" from provider "anthropic"
    Then the verdict should be "use_distillation"
    And the distillation bullets should only contain bullets from "meta" or same supplier
    And bulletsFilteredByProvenance should be 10

  Scenario: Same supplier allows proprietary teacher to teach proprietary student
    Given a playbook manager with domain "nlp" containing 18 bullets
    And all bullets are from "google" with "proprietary" license
    When I route the query "Analyze sentiment" with student model "gemini-pro" from provider "google"
    Then the verdict should be "use_distillation"
    And bulletsFilteredByProvenance should be 0
    And the distillation bullets count should be 18

  Scenario: Open source teacher can teach any student
    Given a playbook manager with domain "ml_training" containing 30 bullets
    And all bullets are from "meta" with "open_source" license
    When I route the query "Train neural network" with student model "gpt-4" from provider "openai"
    Then the verdict should be "use_distillation"
    And bulletsFilteredByProvenance should be 0

  Scenario: No compatible bullets after provenance filtering triggers teacher fallback
    Given a playbook manager with domain "security" containing 8 bullets
    And all bullets are from "openai" with "proprietary" license
    And allowCrossSupplierProprietary is False
    When I route the query "Audit code" with student model "claude-3" from provider "anthropic"
    Then the verdict should be "use_teacher"
    And the domain should be None
    And bulletsFilteredByProvenance should be 8

  Scenario: Refresh domain registry updates available domains
    Given a playbook manager with domain "frontend" containing 10 bullets
    And the router has been initialized
    When I add a new playbook with domain "backend" containing 12 bullets
    And I refresh the router
    Then getAllDomains should return ["frontend", "backend"]

  Scenario: Generate system prompt with section headers and helpful indicators
    Given a playbook manager with domain "testing" containing 20 bullets
    And 5 bullets in section "strategies_and_hard_rules" with helpfulCount 6
    And 5 bullets in section "code_snippets" with helpfulCount 2
    And maxBulletsInPrompt is 20
    And includeSectionHeaders is True
    When I route the query "Write unit tests"
    Then the system prompt should contain "## Strategies & Rules"
    And the system prompt should contain "## Code Patterns"
    And the system prompt should contain "[highly validated]" for bullets with helpfulCount >= 5

  Scenario: Limit bullets in system prompt when exceeding maximum
    Given a playbook manager with domain "devops" containing 50 bullets
    And maxBulletsInPrompt is 20
    When I route the query "Deploy application"
    Then the distillation bullets count in system prompt should be at most 20

  Scenario: Detect supplier from model name
    Given a student model "gpt-4o-mini"
    When I route the query "Generate code"
    Then the studentProvenance supplier should be "openai"

  Scenario: Detect supplier from provider when model name is unknown
    Given a student model "custom-model-v1" from provider "anthropic"
    When I route the query "Analyze text"
    Then the studentProvenance supplier should be "anthropic"

  Scenario: Classify open source license from model name
    Given a student model "llama3-8b"
    When I route the query "Summarize document"
    Then the studentProvenance licenseCategory should be "open_source"

  Scenario: Recommend teacher supplier matching student provenance
    Given a playbook manager with no domains
    And a student model "gemini-flash" from provider "google"
    When I route the query "Any task"
    Then the verdict should be "use_teacher"
    And recommendedTeacherSupplier should be "google"

  Scenario: Route with no playbooks returns teacher fallback
    Given a playbook manager with no playbooks
    When I route the query "Do something"
    Then the verdict should be "use_teacher"
    And the domain should be None
    And the confidence should be 0.0

  Scenario: Create router with factory function
    Given a playbook manager with domain "api" containing 10 bullets
    And model weights {"gpt-4": 2.0, "gpt-3.5": 1.0}
    And highConfidenceThreshold 0.8
    And lowConfidenceThreshold 0.5
    When I create a router using createRouter factory
    Then the router should be configured with highConfidenceThreshold 0.8
    And the router should be configured with lowConfidenceThreshold 0.5