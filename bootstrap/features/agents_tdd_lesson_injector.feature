Feature: TDD Lesson Injector
  As a caller preparing agent prompts
  I want to retrieve phase-specific TDD lessons
  So that I can inject relevant guidance into the development workflow

  Scenario: Retrieve lessons for the red phase
    Given a TDDLessonInjector instance
    When I request lessons for phase "red"
    Then the returned text contains the heading "## TDD Lessons - RED PHASE"
    And the returned text contains "LESSON-001"
    And the returned text contains "LESSON-002"
    And the returned text contains "LESSON-003"

  Scenario: Retrieve lessons for the green phase
    Given a TDDLessonInjector instance
    When I request lessons for phase "green"
    Then the returned text contains the heading "## TDD Lessons - GREEN PHASE"
    And the returned text contains "LESSON-004"
    And the returned text contains "LESSON-005"
    And the returned text contains "LESSON-006"

  Scenario: Retrieve lessons for the planning phase
    Given a TDDLessonInjector instance
    When I request lessons for phase "planning"
    Then the returned text contains the heading "## TDD Lessons - PLANNING PHASE"
    And the returned text contains "LESSON-007"
    And the returned text contains "LESSON-008"
    And the returned text contains "LESSON-009"

  Scenario: Requesting lessons for an unrecognized phase returns empty string
    Given a TDDLessonInjector instance
    When I request lessons for phase "refactor"
    Then the returned text is empty

  Scenario: Phase argument is case-sensitive
    Given a TDDLessonInjector instance
    When I request lessons for phase "RED"
    Then the returned text is empty

  Scenario: Requesting lessons with an empty phase string returns empty string
    Given a TDDLessonInjector instance
    When I request lessons for phase ""
    Then the returned text is empty