Feature: CLI knowledge learning with audit trail

  Scenario: Add a single piece of knowledge to a playbook
    Given a playbook with ID "playbook-123"
    When the user learns content "Always validate input before processing" in section "strategies_and_hard_rules" with tags ["validation", "security"]
    Then a new bullet is created in playbook "playbook-123" with content "Always validate input before processing"
    And the bullet is recorded as human-created with no model attribution

  Scenario: Adding knowledge emits an audit event with full content
    Given a playbook with ID "playbook-123"
    When the user learns content "Cache results to avoid redundant API calls" in section "patterns" with tags ["performance"]
    Then a "KNOWLEDGE_ADDED" audit event is emitted
    And the audit event payload includes the bullet id, content "Cache results to avoid redundant API calls", section "patterns", tags ["performance"], source "cli", and playbook id "playbook-123"
    And the audit event actor is "cli-user" with actor type "human"

  Scenario: Adding knowledge with a custom actor id
    Given a playbook with ID "playbook-123"
    When the user learns content "Retry transient failures up to 3 times" in section "patterns" with tags [] as actor "alice"
    Then the audit event actor id is "alice"

  Scenario: Import multiple knowledge entries from a markdown file
    Given a markdown file "notes.md" containing two "##" sections titled "Use connection pooling" and "Avoid N+1 queries"
    When the user imports knowledge from "notes.md" into playbook "playbook-123"
    Then two bullets are created in playbook "playbook-123"
    And each bullet's content begins with the section title in bold followed by the section body

  Scenario: Importing from a file merges frontmatter tags with CLI-supplied tags
    Given a markdown file "notes.md" whose section has frontmatter tags ["database"]
    When the user imports knowledge from "notes.md" into playbook "playbook-123" with additional tags ["reviewed"]
    Then the created bullet has tags containing "database" and "reviewed" with no duplicates

  Scenario: Importing from a file uses frontmatter type over the default bullet type
    Given a markdown file "notes.md" whose section frontmatter specifies type "decision"
    When the user imports knowledge from "notes.md" into playbook "playbook-123" with default bullet type "pattern"
    Then the created bullet's section is "decision"

  Scenario: Importing from a nonexistent file fails
    Given the file "missing.md" does not exist
    When the user imports knowledge from "missing.md" into playbook "playbook-123"
    Then a file-not-found error is raised and no bullets are created

  Scenario: Importing from a file without an audit client creates bullets but emits no audit events
    Given a markdown file "notes.md" containing one "##" section titled "Use feature flags for rollout"
    When the user imports knowledge from "notes.md" into playbook "playbook-123" without providing an audit client
    Then one bullet is created in playbook "playbook-123"
    And no audit event is emitted