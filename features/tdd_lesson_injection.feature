Feature: TDD Lesson Injection into Agent Prompts
  As an ACE system
  I want TDD lessons injected into agent prompts
  So that the agent learns from past mistakes during code generation

  Background:
    Given an existing AutonomousTDDAgent in src/agents/autonomous_tdd_agent.py
    And an existing get_all_lessons_for_prompt function in src/agents/tdd_lessons.py
    And tests in tests/test_autonomous_tdd_agent.py

  Scenario: Add _get_tdd_lessons method to TDD agent
    Given AutonomousTDDAgent class exists
    When _get_tdd_lessons method is called with phase="red"
    Then it should return formatted lessons string
    And the string should include anti-patterns to avoid

  Scenario: Inject lessons into RED phase (_write_test)
    Given TDD agent is in RED phase
    When _write_test generates a prompt
    Then the prompt should include TDD lessons section
    And lessons should appear before the test writing instructions

  Scenario: Inject lessons into GREEN phase (_write_minimal_code)
    Given TDD agent is in GREEN phase
    When _write_minimal_code generates a prompt
    Then the prompt should include TDD lessons section
    And lessons should warn about common implementation mistakes

  Scenario: Inject lessons into planning phase (_determine_next_increment)
    Given TDD agent is determining next increment
    When _determine_next_increment generates a prompt
    Then the prompt should include TDD lessons section
    And lessons should guide incremental test selection
