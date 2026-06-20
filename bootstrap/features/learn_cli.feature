Feature: CLI Knowledge Learning with Audit Trail

  Scenario: Add a single piece of knowledge with audit trail
    Given a PlaybookManager instance
    And a LocalAuditClient instance
    And a playbook with ID "playbook-123"
    When learnWithAudit is called with playbookId "playbook-123", content "Always validate user input", section "strategies_and_hard_rules", tags ["security", "validation"], and actorId "alice"
    Then a Bullet is returned with the content "Always validate user input"
    And the Bullet has section "strategies_and_hard_rules"
    And the Bullet has tags ["security", "validation"]
    And an audit event of type KNOWLEDGE_ADDED is emitted with actorId "alice" and actorType "human"
    And the audit event payload contains bulletId, content "Always validate user input", section "strategies_and_hard_rules", tags ["security", "validation"], source "cli", and playbookId "playbook-123"

  Scenario: Add knowledge with default actor ID
    Given a PlaybookManager instance
    And a LocalAuditClient instance
    And a playbook with ID "playbook-456"
    When learnWithAudit is called with playbookId "playbook-456", content "Use caching for performance", section "patterns", and tags ["performance"] without specifying actorId
    Then a Bullet is returned
    And an audit event is emitted with actorId "cli-user"

  Scenario: Import knowledge from a markdown file with sections
    Given a PlaybookManager instance
    And a markdown file at path "/tmp/knowledge.md" containing two sections with titles "Pattern One" and "Pattern Two"
    And a playbook with ID "playbook-789"
    When learnFromFile is called with playbookId "playbook-789", filePath "/tmp/knowledge.md", and bulletType "pattern"
    Then a list of 2 Bullets is returned
    And the first Bullet content starts with "**Pattern One**"
    And the second Bullet content starts with "**Pattern Two**"
    And each Bullet has section "pattern"

  Scenario: Import from file with additional CLI tags
    Given a PlaybookManager instance
    And a markdown file at path "/tmp/rules.md" with a section that has tags ["security"]
    And a playbook with ID "playbook-101"
    When learnFromFile is called with playbookId "playbook-101", filePath "/tmp/rules.md", bulletType "decision", and tags ["imported", "reviewed"]
    Then a list of Bullets is returned
    And each Bullet has tags that include "security", "imported", and "reviewed"

  Scenario: Import from file with audit trail
    Given a PlaybookManager instance
    And a LocalAuditClient instance
    And a markdown file at path "/tmp/snippets.md" with one section titled "Code Example"
    And a playbook with ID "playbook-202"
    When learnFromFile is called with playbookId "playbook-202", filePath "/tmp/snippets.md", bulletType "snippet", auditClient provided, and actorId "bob"
    Then a list of 1 Bullet is returned
    And an audit event of type KNOWLEDGE_ADDED is emitted with actorId "bob" and actorType "human"
    And the audit event payload contains source "file_import" and sourceFile "/tmp/snippets.md"

  Scenario: Import from file without audit client
    Given a PlaybookManager instance
    And a markdown file at path "/tmp/data.md" with one section
    And a playbook with ID "playbook-303"
    When learnFromFile is called with playbookId "playbook-303", filePath "/tmp/data.md", and auditClient is None
    Then a list of 1 Bullet is returned
    And no audit event is emitted

  Scenario: Import fails when file does not exist
    Given a PlaybookManager instance
    And a playbook with ID "playbook-404"
    When learnFromFile is called with playbookId "playbook-404" and filePath "/nonexistent/file.md"
    Then a FileNotFoundError is raised with message "File not found: /nonexistent/file.md"

  Scenario: Import respects bullet type from file frontmatter
    Given a PlaybookManager instance
    And a markdown file at path "/tmp/mixed.md" with a section that has type "decision" in frontmatter
    And a playbook with ID "playbook-505"
    When learnFromFile is called with playbookId "playbook-505", filePath "/tmp/mixed.md", and bulletType "pattern"
    Then a list of Bullets is returned
    And the Bullet has section "decision" from the frontmatter, not "pattern"