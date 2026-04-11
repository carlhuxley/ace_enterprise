Feature: TDD Lesson Injector Helper
  As an ACE system
  I want a helper module to format TDD lessons for prompts
  So that lessons can be easily injected into agent prompts

  Background:
    Given a new TDDLessonInjector class in src/agents/tdd_lesson_injector.py
    And tests in tests/test_tdd_lesson_injector.py

  Scenario: Create lesson injector with default beads path
    When TDDLessonInjector is instantiated without arguments
    Then it should use default beads path .beads/issues.jsonl

  Scenario: Get lessons for RED phase
    Given a TDDLessonInjector instance
    When get_lessons_for_phase is called with phase="red"
    Then it should return a formatted string
    And the string should include "RED PHASE" header
    And the string should include anti-patterns to avoid

  Scenario: Get lessons for GREEN phase
    Given a TDDLessonInjector instance
    When get_lessons_for_phase is called with phase="green"
    Then it should return a formatted string
    And the string should include "GREEN PHASE" header

  Scenario: Get lessons for planning phase
    Given a TDDLessonInjector instance
    When get_lessons_for_phase is called with phase="planning"
    Then it should return a formatted string
    And the string should include "PLANNING PHASE" header

  Scenario: Format includes both static and dynamic lessons
    Given beads file with resolved TDD issues
    When get_lessons_for_phase is called
    Then the result should include lessons from KNOWN_TDD_LESSONS
    And the result should include lessons extracted from beads
