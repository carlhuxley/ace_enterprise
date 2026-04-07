Feature: Batch import from markdown for ace learn command
  As an ACE user
  I want to import knowledge from markdown files using ace learn --file
  So that I can bulk-add documentation and decisions to playbooks

  Background:
    Given an existing ace learn CLI command in src/playbook/learn_cli.py
    And a new MarkdownImporter class to be created in src/playbook/markdown_importer.py
    And test file in tests/test_markdown_importer.py

  Scenario: Parse markdown sections into separate bullets
    Given a markdown file with multiple ## headings
    When I parse the file with MarkdownImporter
    Then each ## section becomes a separate bullet
    And the heading text becomes the bullet title
    And the section content becomes the bullet body

  Scenario: Extract frontmatter metadata
    Given a markdown file with YAML frontmatter
    """
    ---
    tags: architecture, database
    type: decision
    ---
    # Decision: Use PostgreSQL
    """
    When I parse the file with MarkdownImporter
    Then tags should be extracted from frontmatter
    And type should be extracted from frontmatter

  Scenario: Handle ARCHITECTURE_DECISIONS.md format
    Given an architecture decisions markdown file
    With sections containing Status, Context, Decision, Consequences
    When I parse the file with MarkdownImporter
    Then each decision becomes a bullet with type "decision"
    And the ADR structure is preserved in the content

  Scenario: CLI accepts --file flag for batch import
    Given the ace learn command
    When I run "ace learn --file decisions.md --type decision"
    Then the file should be parsed by MarkdownImporter
    And each extracted bullet should be added to the playbook

  Scenario: Support --tags flag with file import
    Given a markdown file without frontmatter tags
    When I run "ace learn --file notes.md --tags review,backend"
    Then the provided tags should be applied to all imported bullets

  Scenario: Mark imported bullets as human-authored
    Given a markdown file to import
    When bullets are created from the file
    Then created_by_model should be set to "human"
    And source_file should contain the original filename
