Feature: Playbook Maintenance

  Scenario: Decaying confidence of stale bullets in an existing playbook
    Given a playbook "pb-001" with a bullet "b-1" last used 120 days ago with confidence 0.5
    When decay_stale_bullets is called for playbook "pb-001" with stale_days 90 and decay_factor 0.1
    Then the call returns 1
    And bullet "b-1" now has confidence 0.4

  Scenario: Bullets used recently are not decayed
    Given a playbook "pb-002" with a bullet "b-2" last used 5 days ago with confidence 0.5
    When decay_stale_bullets is called for playbook "pb-002" with stale_days 90 and decay_factor 0.1
    Then the call returns 0
    And bullet "b-2" still has confidence 0.5

  Scenario: Decaying bullets in a playbook that does not exist
    Given no playbook exists with id "pb-missing"
    When decay_stale_bullets is called for playbook "pb-missing"
    Then the call returns 0

  Scenario: Confidence decay never goes below zero
    Given a playbook "pb-003" with a bullet "b-3" last used 200 days ago with confidence 0.05
    When decay_stale_bullets is called for playbook "pb-003" with stale_days 90 and decay_factor 0.1
    Then the call returns 1
    And bullet "b-3" now has confidence 0.0

  Scenario: Pruning removes old bullets below the confidence threshold
    Given a playbook "pb-004" with a bullet "b-4" created 60 days ago with confidence 0.05
    When prune_low_confidence_bullets is called for playbook "pb-004" with min_confidence 0.1 and min_age_days 30
    Then the call returns 1
    And playbook "pb-004" no longer contains bullet "b-4"

  Scenario: Pruning keeps young low-confidence bullets
    Given a playbook "pb-005" with a bullet "b-5" created 5 days ago with confidence 0.05
    When prune_low_confidence_bullets is called for playbook "pb-005" with min_confidence 0.1 and min_age_days 30
    Then the call returns 0
    And playbook "pb-005" still contains bullet "b-5"

  Scenario: Running full maintenance across all playbooks
    Given playbooks "pb-006" and "pb-007" exist in the playbook manager
    And "pb-006" has a stale bullet eligible for decay
    And "pb-007" has an old low-confidence bullet eligible for pruning
    When run_maintenance is called with no specific playbook_id
    Then the result reports playbooks_processed as 2
    And the result reports bullets_decayed as at least 1
    And the result reports bullets_pruned as at least 1

  Scenario: Running maintenance on a single specified playbook
    Given playbooks "pb-008" and "pb-009" exist in the playbook manager
    And "pb-009" has a stale bullet eligible for decay
    When run_maintenance is called with playbook_id "pb-009"
    Then the result reports playbooks_processed as 1
    And the result reports bullets_decayed as at least 1