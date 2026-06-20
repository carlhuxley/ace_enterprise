Feature: Decision Record Generation
  As a system that documents architectural decisions
  I want to create and save decision records
  So that I can maintain institutional knowledge about features built

  Scenario: Create a minimal decision record
    Given a feature name "User Authentication"
    And a date of 2024-01-15
    When I create a DecisionRecord
    Then the record has featureName "User Authentication"
    And the record has date 2024-01-15
    And the record has status "Accepted"
    And the record has empty lists for testsGenerated, filesCreated, designDecisions, patternsApplied, patternsLearned, and aiModels

  Scenario: Generate markdown for a basic decision record
    Given a DecisionRecord with featureName "Payment Processing"
    And date 2024-03-20
    And status "Accepted"
    When I call toMarkdown
    Then the output contains "# Payment Processing"
    And the output contains "**Date:** 2024-03-20"
    And the output contains "**Status:** Accepted"
    And the output contains "## Context"
    And the output contains "## Decision"
    And the output contains "## Implementation"

  Scenario: Generate markdown with full metadata and contributors
    Given a DecisionRecord with featureName "API Gateway"
    And date 2024-02-10
    And humanContributor "Alice Smith"
    And aiModels ["GPT-4", "Claude"]
    When I call toMarkdown
    Then the output contains "**Author:** Alice Smith"
    And the output contains "**AI Models:** GPT-4, Claude"

  Scenario: Generate markdown with gherkin scenarios and requirement
    Given a DecisionRecord with featureName "Shopping Cart"
    And requirement "Users must be able to add items to cart"
    And gherkinScenarios containing "Scenario: Add item to cart"
    When I call toMarkdown
    Then the output contains "**Requirement:** Users must be able to add items to cart"
    And the output contains "**Gherkin Scenarios:**"
    And the output contains "```gherkin"
    And the output contains "Scenario: Add item to cart"

  Scenario: Generate markdown with implementation details
    Given a DecisionRecord with featureName "Email Service"
    And implementationSummary "Implemented async email sending with retry logic"
    And filesCreated ["email_service.py", "email_config.py"]
    And testsGenerated ["test_email_send", "test_email_retry"]
    And designDecisions ["Use async/await pattern", "Implement exponential backoff"]
    When I call toMarkdown
    Then the output contains "Implemented async email sending with retry logic"
    And the output contains "**Files Created:**"
    And the output contains "- `email_service.py`"
    And the output contains "- `email_config.py`"
    And the output contains "**Tests Generated:**"
    And the output contains "- `test_email_send`"
    And the output contains "**Design Decisions:**"
    And the output contains "- Use async/await pattern"

  Scenario: Generate markdown with patterns applied and learned
    Given a DecisionRecord with featureName "Cache Layer"
    And patternsApplied ["Repository Pattern", "Decorator Pattern"]
    And patternsLearned ["Cache invalidation strategies", "TTL management"]
    When I call toMarkdown
    Then the output contains "## Patterns"
    And the output contains "**Applied:**"
    And the output contains "- Repository Pattern"
    And the output contains "**Learned:**"
    And the output contains "- Cache invalidation strategies"

  Scenario: Save decision record with auto-generated filename
    Given a DecisionRecord with featureName "User Profile"
    And date 2024-05-15
    When I call save with directory "/tmp/decisions" and no filename
    Then a file is created at "/tmp/decisions/2024-05-15-user-profile.md"
    And the file contains the markdown output

  Scenario: Save decision record with custom filename
    Given a DecisionRecord with featureName "Notification System"
    When I call save with directory "/tmp/decisions" and filename "custom-adr.md"
    Then a file is created at "/tmp/decisions/custom-adr.md"
    And the file contains the markdown output

  Scenario: Generate ADR from TDD result
    Given featureName "Search Feature"
    And gherkinContent "Scenario: Search by keyword"
    And filesCreated ["search.py", "search_index.py"]
    And testsGenerated ["test_search_keyword", "test_search_empty"]
    And patternsLearned ["Inverted index pattern", "Query optimization"]
    And humanContributor "Bob Jones"
    And aiModels ["GPT-4"]
    When I call generateAdrFromTddResult
    Then a DecisionRecord is returned
    And the record has featureName "Search Feature"
    And the record has gherkinScenarios "Scenario: Search by keyword"
    And the record has implementationSummary "Built Search Feature feature using Gherkin-driven TDD"
    And the record has filesCreated ["search.py", "search_index.py"]
    And the record has testsGenerated ["test_search_keyword", "test_search_empty"]
    And the record has designDecisions containing "Used Test-Driven Development (RED → GREEN → REFACTOR)"
    And the record has patternsLearned ["Inverted index pattern", "Query optimization"]
    And the record has status "Accepted"
    And the record has humanContributor "Bob Jones"
    And the record has aiModels ["GPT-4"]

  Scenario: Feature name slug generation handles spaces and underscores
    Given a DecisionRecord with featureName "User_Login System"
    And date 2024-06-01
    When I call save with directory "/tmp/decisions" and no filename
    Then a file is created at "/tmp/decisions/2024-06-01-user-login-system.md"