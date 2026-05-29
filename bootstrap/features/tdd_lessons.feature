Feature: TDD Lessons
  Manages TDD anti-patterns learned from past failures and formats them for prompt injection

  Scenario: Prompt lessons return a non-empty formatted string
    Given a lessons manager with known anti-patterns loaded
    When the lessons are formatted for prompt injection
    Then the result is a non-empty string
    And the result contains a section heading for anti-patterns

  Scenario: Categorize import error output as import failure
    Given an error output containing "ImportError: No module named 'foo'"
    And test code "import foo"
    When the failure is categorized
    Then the category indicates an import error

  Scenario: Categorize syntax error output as syntax failure
    Given an error output containing "SyntaxError: invalid syntax"
    And test code "function test() {}"
    When the failure is categorized
    Then the category indicates a syntax error

  Scenario: Categorize mocking pattern in test code as mocking failure
    Given an error output containing "AssertionError: Expected mock to be called"
    And test code containing "assert_called_once" and "patch"
    When the failure is categorized
    Then the category indicates a mocking error

  Scenario: Extract lessons from resolved records only
    Given a collection of 3 records where 2 are resolved and 1 is open
    And all 3 records are tagged as tdd-related
    When lessons are extracted from the collection
    Then exactly 2 lessons are returned

  Scenario: Missing lesson source returns empty list
    Given a lesson source that does not exist
    When lessons are extracted from the source
    Then an empty list is returned
