Feature: Documentation Rubric Evaluation
  As a caller of the documentation rubric
  I want to score Markdown documentation text
  So that I can assess its completeness, clarity, examples, and formatting

  Background:
    Given a documentation rubric named "documentation"
    And its scoring dimensions are:
      | dimension     | weight | description                                         |
      | completeness  | 0.30   | Has headings and substantive paragraphs             |
      | clarity       | 0.25   | Reasonable line lengths; not excessively terse      |
      | examples      | 0.25   | Contains fenced code blocks                         |
      | formatting    | 0.20   | Markdown headings and bullet lists present          |

  Scenario: Well-structured documentation scores highly across all dimensions
    Given the following Markdown text:
      """
      # Getting Started

      This library helps you parse configuration files quickly and safely
      using a simple declarative syntax that most developers already know.

      - Install the package with pip
      - Import the parser module
      - Call parse() on your config file

      from mylib import parse
      parse("config.yaml")
      """
    When the rubric scores the text against the "completeness" dimension
    Then the score is 100.0
    When the rubric scores the text against the "formatting" dimension
    Then the score is 100.0

  Scenario: Documentation with a heading but only one short paragraph gets partial completeness credit
    Given the following Markdown text:
      """
      # Overview

      Short intro.
      """
    When the rubric scores the text against the "completeness" dimension
    Then the score is 50.0

  Scenario: Plain text with no headings and no paragraph breaks scores zero completeness
    Given the following Markdown text:
      """
      just a single line of text with no structure at all
      """
    When the rubric scores the text against the "completeness" dimension
    Then the score is 0.0

  Scenario: Lines with an ideal average length score maximum clarity
    Given a Markdown text whose non-blank lines average between 40 and 100 characters
    When the rubric scores the text against the "clarity" dimension
    Then the score is 100.0

  Scenario: Very short, terse lines score low clarity
    Given the following Markdown text:
      """
      ok
      yes
      """
    When the rubric scores the text against the "clarity" dimension
    Then the score is 20.0

  Scenario: Text with no fenced code blocks scores zero on examples
    Given the following Markdown text:
      """
      # Usage

      Call the function with your arguments to get a result.
      """
    When the rubric scores the text against the "examples" dimension
    Then the score is 0.0

  Scenario: Text with two fenced code blocks scores highly on examples
    Given a Markdown text containing 2 fenced code blocks
    When the rubric scores the text against the "examples" dimension
    Then the score is 100.0

  Scenario: Text with neither headings nor bullet lists scores zero formatting
    Given the following Markdown text:
      """
      This is plain prose with no markdown structure whatsoever, just words.
      """
    When the rubric scores the text against the "formatting" dimension
    Then the score is 0.0