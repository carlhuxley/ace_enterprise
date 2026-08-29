Feature: Markdown importer for playbook knowledge

  Scenario: Parsing a markdown document with multiple headings into separate bullets
    Given the markdown content:
      """
      ## First Pattern
      This is the first pattern's content.

      ## Second Pattern
      This is the second pattern's content.
      """
    When the content is parsed
    Then 2 bullets are returned
    And the first bullet has title "First Pattern" and content "This is the first pattern's content."
    And the second bullet has title "Second Pattern" and content "This is the second pattern's content."

  Scenario: Parsing markdown with no ## headings yields no bullets
    Given the markdown content:
      """
      Just a plain paragraph with no headings.
      """
    When the content is parsed
    Then an empty list of bullets is returned

  Scenario: Frontmatter tags as a comma-separated string are applied to every bullet
    Given the markdown content:
      """
      ---
      tags: security, auth, backend
      ---
      ## Login Flow
      Describes the login flow.

      ## Token Refresh
      Describes token refresh.
      """
    When the content is parsed
    Then 2 bullets are returned
    And every bullet has tags ["security", "auth", "backend"]

  Scenario: Frontmatter tags as a YAML list are applied to every bullet
    Given the markdown content:
      """
      ---
      tags:
        - infra
        - deploy
      ---
      ## Rollout Steps
      Details the rollout steps.
      """
    When the content is parsed
    Then 1 bullet is returned
    And the bullet has tags ["infra", "deploy"]

  Scenario: Frontmatter type is applied to every bullet
    Given the markdown content:
      """
      ---
      type: decision
      ---
      ## Use Postgres
      We chose Postgres for durability.
      """
    When the content is parsed
    Then the bullet has type "decision"

  Scenario: Content without frontmatter produces bullets with no type key and no tags
    Given the markdown content:
      """
      ## Standalone Note
      A note with no frontmatter at all.
      """
    When the content is parsed
    Then the bullet has an empty tags list
    And the bullet does not include a "type" field

  Scenario: Malformed YAML frontmatter is ignored without raising an error
    Given the markdown content:
      """
      ---
      tags: [unclosed, bracket
      ---
      ## Broken Frontmatter Section
      Content should still be extracted.
      """
    When the content is parsed
    Then 1 bullet is returned
    And the bullet has title "Broken Frontmatter Section"
    And the bullet has an empty tags list

  Scenario: Parsing a file attaches the source filename to each bullet
    Given a markdown file named "notes.md" containing:
      """
      ## Deployment Checklist
      Verify all services are healthy before deploying.
      """
    When the file is parsed
    Then 1 bullet is returned
    And the bullet has source_file "notes.md"