Feature: Playbook Maintenance Operations
  Maintenance operations for playbook health including confidence decay and pruning.

  Scenario: Decay confidence of stale bullets in a playbook
    Given a playbook manager with playbook "play-001"
    And playbook "play-001" has bullets with lastUsed older than 90 days
    And those bullets have confidenceScore of 0.5
    When decayStaleBullets is called with playbookId "play-001", staleDays 90, and decayFactor 0.1
    Then the function returns 1 or more affected bullets
    And the stale bullets have confidenceScore reduced by 0.1

  Scenario: Decay returns zero when playbook does not exist
    Given a playbook manager without playbook "nonexistent"
    When decayStaleBullets is called with playbookId "nonexistent", staleDays 90, and decayFactor 0.1
    Then the function returns 0

  Scenario: Decay does not affect recently used bullets
    Given a playbook manager with playbook "play-002"
    And playbook "play-002" has bullets with lastUsed within the last 30 days
    When decayStaleBullets is called with playbookId "play-002", staleDays 90, and decayFactor 0.1
    Then the function returns 0

  Scenario: Decay confidence cannot go below zero
    Given a playbook manager with playbook "play-003"
    And playbook "play-003" has a stale bullet with confidenceScore 0.05
    When decayStaleBullets is called with playbookId "play-003", staleDays 90, and decayFactor 0.1
    Then the function returns 1
    And the bullet has confidenceScore of 0.0

  Scenario: Prune low confidence bullets that are old enough
    Given a playbook manager with playbook "play-004"
    And playbook "play-004" has bullets with confidenceScore 0.05 and createdAt older than 30 days
    When pruneLowConfidenceBullets is called with playbookId "play-004", minConfidence 0.1, and minAgeDays 30
    Then the function returns 1 or more removed bullets
    And the playbook totalBullets count is reduced accordingly

  Scenario: Prune returns zero when playbook does not exist
    Given a playbook manager without playbook "nonexistent"
    When pruneLowConfidenceBullets is called with playbookId "nonexistent", minConfidence 0.1, and minAgeDays 30
    Then the function returns 0

  Scenario: Prune does not remove bullets that are too new
    Given a playbook manager with playbook "play-005"
    And playbook "play-005" has bullets with confidenceScore 0.05 and createdAt within the last 10 days
    When pruneLowConfidenceBullets is called with playbookId "play-005", minConfidence 0.1, and minAgeDays 30
    Then the function returns 0

  Scenario: Prune does not remove bullets with sufficient confidence
    Given a playbook manager with playbook "play-006"
    And playbook "play-006" has bullets with confidenceScore 0.5 and createdAt older than 30 days
    When pruneLowConfidenceBullets is called with playbookId "play-006", minConfidence 0.1, and minAgeDays 30
    Then the function returns 0

  Scenario: Run full maintenance cycle on a specific playbook
    Given a playbook manager with playbook "play-007"
    And playbook "play-007" has stale bullets and low confidence old bullets
    When runMaintenance is called with playbookId "play-007", decayStaleDays 90, decayFactor 0.1, pruneThreshold 0.1, and pruneMinAgeDays 30
    Then the function returns a dictionary with playbooksProcessed equal to 1
    And the dictionary contains bulletsDecayed greater than or equal to 0
    And the dictionary contains bulletsPruned greater than or equal to 0

  Scenario: Run full maintenance cycle on all playbooks
    Given a playbook manager with playbooks "play-008" and "play-009"
    When runMaintenance is called with playbookId None, decayStaleDays 90, decayFactor 0.1, pruneThreshold 0.1, and pruneMinAgeDays 30
    Then the function returns a dictionary with playbooksProcessed equal to 2
    And the dictionary contains bulletsDecayed greater than or equal to 0
    And the dictionary contains bulletsPruned greater than or equal to 0
