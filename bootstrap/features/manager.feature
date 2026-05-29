Feature: Playbook Manager
  Manages playbooks and bullets in memory with versioning and feedback tracking

  Scenario: Create a new playbook returns it with initial state
    Given a PlaybookManager instance
    When a playbook is created with domain "python-testing"
    Then a playbook is returned
    And the playbook has a non-empty ID
    And the total_bullets count is 0

  Scenario: Add a bullet returns it with a generated ID
    Given a PlaybookManager with an existing playbook "pb-test"
    When a bullet is added with content "Always validate inputs" and section "strategies_and_hard_rules"
    Then a bullet is returned
    And the bullet has a non-empty ID
    And the bullet content is "Always validate inputs"

  Scenario: Get-or-create returns existing playbook unchanged
    Given a PlaybookManager with playbook "pb-existing" already created
    When get_or_create is called with playbook_id "pb-existing"
    Then the existing playbook is returned without modification

  Scenario: Get playbook returns None for unknown ID
    Given a PlaybookManager instance
    When get_playbook is called with "pb-unknown"
    Then None is returned

  Scenario: Update feedback as helpful increments helpful_count
    Given a PlaybookManager with playbook "pb-feedback" containing bullet "ctx-001"
    When bullet feedback "helpful" is recorded for "ctx-001"
    Then the bullet helpful_count increases by 1

  Scenario: Remove an existing bullet decrements total count
    Given a PlaybookManager with playbook "pb-remove" containing 2 bullets
    When one bullet is removed
    Then true is returned
    And the total bullet count decreases by 1
