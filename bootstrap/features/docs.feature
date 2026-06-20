Feature: Documentation Rubric

  Scenario: Get rubric name
    Given a DocumentationRubric instance
    When the name property is accessed
    Then it returns "documentation"

  Scenario: Get rubric dimensions
    Given a DocumentationRubric instance
    When the dimensions property is accessed
    Then it returns 4 dimensions
    And dimension 1 has name "completeness" with weight 0.30
    And dimension 2 has name "clarity" with weight 0.25
    And dimension 3 has name "examples" with weight 0.25
    And dimension 4 has name "formatting" with weight 0.20

  Scenario: Score completeness dimension with full content
    Given a DocumentationRubric instance
    And output text with heading "# Introduction", 3 paragraphs, and 50 words
    When scoring dimension "completeness"
    Then the score is 100.0

  Scenario: Score completeness dimension with minimal content
    Given a DocumentationRubric instance
    And output text "Short text"
    When scoring dimension "completeness"
    Then the score is 0.0

  Scenario: Score clarity dimension with optimal line length
    Given a DocumentationRubric instance
    And output text with 5 lines averaging 60 characters each
    When scoring dimension "clarity"
    Then the score is 100.0

  Scenario: Score clarity dimension with very short lines
    Given a DocumentationRubric instance
    And output text with lines averaging 8 characters each
    When scoring dimension "clarity"
    Then the score is 20.0

  Scenario: Score examples dimension with code blocks
    Given a DocumentationRubric instance
    And output text containing 2 fenced code blocks with triple backticks
    When scoring dimension "examples"
    Then the score is 100.0

  Scenario: Score examples dimension without code blocks
    Given a DocumentationRubric instance
    And output text "Plain text without code"
    When scoring dimension "examples"
    Then the score is 0.0

  Scenario: Score formatting dimension with headings and lists
    Given a DocumentationRubric instance
    And output text with markdown heading "## Title" and bullet list "- item"
    When scoring dimension "formatting"
    Then the score is 100.0

  Scenario: Score formatting dimension with only headings
    Given a DocumentationRubric instance
    And output text "# Heading\nSome content"
    When scoring dimension "formatting"
    Then the score is 50.0

  Scenario: Score unknown dimension
    Given a DocumentationRubric instance
    And output text "Any content"
    When scoring dimension "unknown"
    Then the score is 0.0