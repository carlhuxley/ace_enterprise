Feature: Markdown Importer

  Scenario: Parse markdown with single heading and content
    Given a markdown content with "## Introduction" heading and "This is the intro text." content
    When the importer parses the markdown
    Then the result contains 1 bullet
    And the bullet has title "Introduction"
    And the bullet has content "This is the intro text."
    And the bullet has tags as empty list
    And the bullet has createdByModel "human"

  Scenario: Parse markdown with multiple headings
    Given a markdown content with three headings "## First", "## Second", and "## Third"
    And "First" has content "Content one."
    And "Second" has content "Content two."
    And "Third" has content "Content three."
    When the importer parses the markdown
    Then the result contains 3 bullets
    And bullet 0 has title "First" and content "Content one."
    And bullet 1 has title "Second" and content "Content two."
    And bullet 2 has title "Third" and content "Content three."

  Scenario: Parse markdown with YAML frontmatter containing comma-separated tags
    Given a markdown content with frontmatter "---\ntags: security, performance\n---\n"
    And a heading "## Overview" with content "System overview."
    When the importer parses the markdown
    Then the result contains 1 bullet
    And the bullet has tags ["security", "performance"]
    And the bullet has title "Overview"

  Scenario: Parse markdown with YAML frontmatter containing list tags
    Given a markdown content with frontmatter "---\ntags:\n  - database\n  - api\n---\n"
    And a heading "## Design" with content "Design details."
    When the importer parses the markdown
    Then the result contains 1 bullet
    And the bullet has tags ["database", "api"]

  Scenario: Parse markdown with frontmatter type field
    Given a markdown content with frontmatter "---\ntype: decision\n---\n"
    And a heading "## Status" with content "Accepted"
    When the importer parses the markdown
    Then the result contains 1 bullet
    And the bullet has type "decision"

  Scenario: Parse markdown file with source file tracking
    Given a markdown content "## Test\nTest content."
    When the importer parses the markdown with sourceFile "example.md"
    Then the result contains 1 bullet
    And the bullet has sourceFile "example.md"

  Scenario: Parse markdown with no headings
    Given a markdown content "Just some text without headings."
    When the importer parses the markdown
    Then the result contains 0 bullets

  Scenario: Parse markdown with invalid YAML frontmatter
    Given a markdown content with malformed frontmatter "---\ntags: [unclosed\n---\n"
    And a heading "## Content" with content "Some text."
    When the importer parses the markdown
    Then the result contains 1 bullet
    And the bullet has tags as empty list
    And the bullet has title "Content"