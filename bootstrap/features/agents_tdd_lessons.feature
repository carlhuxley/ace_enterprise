Feature: TDD Lessons and Anti-Patterns
  As a caller building TDD prompts and analyzing test failures
  I want to retrieve known anti-patterns and categorize failures
  So that I can inject guidance into LLM prompts and learn from past mistakes

  Scenario: Retrieve formatted anti-patterns for prompt injection
    When I call get_lessons_for_prompt with no arguments
    Then the returned string contains the heading "## TDD Anti-Patterns to Avoid"
    And the returned string contains "mocking_error: Mocking the public method you're trying to test caching on"
    And the returned string contains "Bad example:"
    And the returned string contains "Good example:"

  Scenario: Categorize failure as an import error
    Given error output "ModuleNotFoundError: No module named 'foo'"
    And test code "import foo"
    When I call categorize_failure with the error output and test code
    Then the result is "import_error"

  Scenario: Categorize failure as a syntax error
    Given error output "SyntaxError: invalid syntax"
    And test code "def broken(:"
    When I call categorize_failure with the error output and test code
    Then the result is "syntax_error"

  Scenario: Categorize failure as a mocking error based on test code patterns
    Given error output "AssertionError: expected call not found"
    And test code "with patch.object(obj, 'method') as mock: mock.assert_called_once()"
    When I call categorize_failure with the error output and test code
    Then the result is "mocking_error"

  Scenario: Categorize an unrecognized failure as an implementation bug
    Given error output "Something went wrong"
    And test code "assert True"
    When I call categorize_failure with the error output and test code
    Then the result is "implementation_bug"

  Scenario: LessonExtractor returns no lesson for an unresolved issue
    Given a LessonExtractor with any beads path
    And a beads issue with status "open" and intervention_steps ["Fix the mock"]
    When I call extract_from_issue with the issue
    Then the result is None

  Scenario: LessonExtractor extracts a lesson from a resolved issue with intervention steps
    Given a LessonExtractor with any beads path
    And a beads issue with status "resolved", labels ["tdd", "mocking"], title "TDD build failed: cache not respected", and intervention_steps ["Mock the fetch method", "Verify call count"]
    When I call extract_from_issue with the issue
    Then the result is a lesson with category "mocking_error"
    And the result has anti_pattern "cache not respected"
    And the result has correct_pattern "Mock the fetch method; Verify call count"

  Scenario: LessonExtractor returns an empty list when the beads file does not exist
    Given a LessonExtractor with beads_path pointing to a nonexistent file
    When I call extract_all_from_beads
    Then the result is an empty list

  Scenario: Combined lessons include a count of dynamically learned failures
    Given a beads issues file containing one resolved "tdd"-labeled issue with intervention_steps ["Use assertCountEqual"]
    When I call get_all_lessons_for_prompt with the path to that beads file
    Then the returned string contains "3 core lessons + 1 learned from past failures"