Feature: TDD agent self-healing and failure recording
  As an ACE system
  I want the TDD agent to automatically record failures and learn from them
  So that the system continuously improves and reduces intervention rate

  Background:
    Given an existing AutonomousTDDAgent in src/agents/autonomous_tdd_agent.py
    And a new TDDFailureRecorder class to be created in src/agents/tdd_failure_recorder.py
    And test file in tests/test_tdd_failure_recorder.py

  Scenario: Record failed TDD cycle to experiment logger
    Given a TDD cycle that failed after max retries
    When the failure is recorded
    Then ExperimentLogger.log_experiment should be called with result="FAILED"
    And the task_data should include the feature requirement
    And curator_data should include manual_intervention_required=True

  Scenario: Create beads issue for TDD failure
    Given a TDD cycle failure with error details
    When recording the failure
    Then a bug issue should be created in .beads/issues.jsonl
    And the issue should have issue_type="bug"
    And the issue should include the error message and stack trace
    And the issue should have suggested_fix from LLM analysis

  Scenario: Add troubleshooting bullet to playbook
    Given a TDD failure with identifiable pattern
    When the failure is recorded
    Then a bullet should be added to the playbook troubleshooting section
    And the bullet should describe the failure pattern
    And the bullet should include prevention guidance

  Scenario: Track intervention source
    Given a TDD build that required intervention
    When recording the intervention
    Then intervention_source should be one of: human, ai_assistant, self_healed
    And the intervention steps should be recorded if provided

  Scenario: Calculate intervention rate metric
    Given multiple TDD build experiments in the log
    When calculating intervention_rate
    Then it should equal (human + ai_assistant) / total_builds
    And the metric should be available for reporting
