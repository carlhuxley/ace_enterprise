Feature: TDD Lesson Injector
  As a caller of the TDD Lesson Injector
  I want to retrieve phase-specific TDD lessons
  So that I can provide appropriate guidance based on the development phase

  Scenario: Retrieve lessons for red phase
    Given a TDDLessonInjector instance
    When I call get_lessons_for_phase with "red"
    Then the result contains "## TDD Lessons - RED PHASE"
    And the result contains "[LESSON-001]: Don't test internal state or private methods"
    And the result contains "[LESSON-002]: Mock only external dependencies, not the system under test"
    And the result contains "[LESSON-003]: Use specific expected values, not just truthiness checks"
    And the result contains "Lessons for red phase..."

  Scenario: Retrieve lessons for green phase
    Given a TDDLessonInjector instance
    When I call get_lessons_for_phase with "green"
    Then the result contains "## TDD Lessons - GREEN PHASE"
    And the result contains "[LESSON-004]: Implement only what's needed to pass the test"
    And the result contains "[LESSON-005]: Always write the failing test before implementation"
    And the result contains "[LESSON-006]: Keep it simple and minimal"
    And the result contains "Lessons for green phase..."

  Scenario: Retrieve lessons for planning phase
    Given a TDDLessonInjector instance
    When I call get_lessons_for_phase with "planning"
    Then the result contains "## TDD Lessons - PLANNING PHASE"
    And the result contains "[LESSON-007]: Begin with the most basic happy path"
    And the result contains "[LESSON-008]: Each test should verify one specific behavior"
    And the result contains "[LESSON-009]: Add complexity step by step"
    And the result contains "Lessons for planning phase..."

  Scenario: Retrieve lessons for unrecognized phase
    Given a TDDLessonInjector instance
    When I call get_lessons_for_phase with "refactor"
    Then the result is an empty string

  Scenario: Retrieve lessons for empty phase string
    Given a TDDLessonInjector instance
    When I call get_lessons_for_phase with ""
    Then the result is an empty string

  Scenario: Create multiple injector instances independently
    Given a TDDLessonInjector instance named injector1
    And a TDDLessonInjector instance named injector2
    When I call get_lessons_for_phase with "red" on injector1
    And I call get_lessons_for_phase with "green" on injector2
    Then injector1 returns content containing "RED PHASE"
    And injector2 returns content containing "GREEN PHASE"