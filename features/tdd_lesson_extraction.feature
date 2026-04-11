Feature: TDD Lesson Extraction from Beads
  As an ACE system
  I want to extract lessons from resolved TDD failures in beads
  So that the system learns from past mistakes automatically

  Background:
    Given an existing TDDLesson dataclass in src/agents/tdd_lessons.py
    And an existing TDDFailureCategory enum in src/agents/tdd_lessons.py
    And new LessonExtractor class to add in src/agents/tdd_lessons.py
    And tests in tests/test_tdd_lessons.py

  Scenario: Extract lesson from resolved beads issue
    Given a beads issue with status "resolved"
    And the issue has intervention_steps describing the fix
    And the issue has labels including "tdd"
    When extract_from_issue is called
    Then it should return a TDDLesson object
    And the lesson category should match the issue labels
    And the anti_pattern should be derived from the issue title
    And the correct_pattern should be derived from intervention_steps

  Scenario: Skip unresolved issues
    Given a beads issue with status "open"
    When extract_from_issue is called
    Then it should return None

  Scenario: Skip issues without intervention steps
    Given a resolved beads issue without intervention_steps
    When extract_from_issue is called
    Then it should return None

  Scenario: Map labels to failure categories
    Given an issue with label "import"
    When _category_from_labels is called
    Then it should return TDDFailureCategory.IMPORT_ERROR

    Given an issue with label "mocking_error"
    When _category_from_labels is called
    Then it should return TDDFailureCategory.MOCKING_ERROR

  Scenario: Extract all lessons from beads file
    Given a .beads/issues.jsonl file with multiple TDD issues
    And some issues are resolved with intervention_steps
    And some issues are still open
    When extract_all_from_beads is called
    Then it should return only lessons from resolved TDD issues

  Scenario: Handle missing beads file gracefully
    Given no .beads/issues.jsonl file exists
    When extract_all_from_beads is called
    Then it should return an empty list
    And no error should be raised

  Scenario: Combined static and dynamic lessons
    Given KNOWN_TDD_LESSONS contains 3 hardcoded lessons
    And beads file contains 2 resolved TDD issues
    When get_all_lessons_for_prompt is called
    Then the result should include all 5 lessons
    And the result should note "3 core lessons + 2 learned from past failures"
