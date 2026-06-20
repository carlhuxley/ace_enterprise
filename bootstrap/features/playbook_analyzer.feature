Feature: Playbook Reliability Analysis

  Scenario: No TDD cycle records exist for playbook
    Given an ExperimentLogger with no records
    And a PlaybookManager
    And a PlaybookReliabilityAnalyzer initialized with the logger and manager
    When bulletReliability is called with playbookId "playbook-001"
    Then an empty list is returned

  Scenario: Bullets with zero retrievals are excluded
    Given an ExperimentLogger with TDD cycle records for playbook "playbook-002":
      | result  | retryCount | retrievedBulletIds |
      | SUCCESS | 0           | []                   |
      | FAILURE | 1           | []                   |
    And a PlaybookManager
    And a PlaybookReliabilityAnalyzer initialized with the logger and manager
    When bulletReliability is called with playbookId "playbook-002"
    Then an empty list is returned

  Scenario: Single bullet retrieved once with first-pass success
    Given an ExperimentLogger with TDD cycle records for playbook "playbook-003":
      | result  | retryCount | retrievedBulletIds |
      | SUCCESS | 0           | ["bullet-A"]         |
    And a PlaybookManager
    And a PlaybookReliabilityAnalyzer initialized with the logger and manager
    When bulletReliability is called with playbookId "playbook-003"
    Then a list with 1 BulletReliability is returned:
      | bulletId | timesRetrieved | firstPassCount | firstPassRate |
      | bullet-A  | 1               | 1                | 1.0             |

  Scenario: Single bullet retrieved once without first-pass success
    Given an ExperimentLogger with TDD cycle records for playbook "playbook-004":
      | result  | retryCount | retrievedBulletIds |
      | SUCCESS | 1           | ["bullet-B"]         |
    And a PlaybookManager
    And a PlaybookReliabilityAnalyzer initialized with the logger and manager
    When bulletReliability is called with playbookId "playbook-004"
    Then a list with 1 BulletReliability is returned:
      | bulletId | timesRetrieved | firstPassCount | firstPassRate |
      | bullet-B  | 1               | 0                | 0.0             |

  Scenario: Multiple bullets with varying first-pass rates sorted descending
    Given an ExperimentLogger with TDD cycle records for playbook "playbook-005":
      | result  | retryCount | retrievedBulletIds |
      | SUCCESS | 0           | ["bullet-X"]         |
      | SUCCESS | 1           | ["bullet-X"]         |
      | SUCCESS | 0           | ["bullet-Y"]         |
      | SUCCESS | 0           | ["bullet-Y"]         |
      | FAILURE | 2           | ["bullet-Z"]         |
    And a PlaybookManager
    And a PlaybookReliabilityAnalyzer initialized with the logger and manager
    When bulletReliability is called with playbookId "playbook-005"
    Then a list with 3 BulletReliability is returned sorted by firstPassRate descending:
      | bulletId | timesRetrieved | firstPassCount | firstPassRate |
      | bullet-Y  | 2               | 2                | 1.0             |
      | bullet-X  | 2               | 1                | 0.5             |
      | bullet-Z  | 1               | 0                | 0.0             |

  Scenario: Multiple bullets retrieved in same cycle
    Given an ExperimentLogger with TDD cycle records for playbook "playbook-006":
      | result  | retryCount | retrievedBulletIds    |
      | SUCCESS | 0           | ["bullet-M", "bullet-N"]|
      | FAILURE | 0           | ["bullet-M"]            |
    And a PlaybookManager
    And a PlaybookReliabilityAnalyzer initialized with the logger and manager
    When bulletReliability is called with playbookId "playbook-006"
    Then a list with 2 BulletReliability is returned sorted by firstPassRate descending:
      | bulletId | timesRetrieved | firstPassCount | firstPassRate |
      | bullet-N  | 1               | 1                | 1.0             |
      | bullet-M  | 2               | 1                | 0.5             |

  Scenario: First-pass success requires both SUCCESS result and zero retryCount
    Given an ExperimentLogger with TDD cycle records for playbook "playbook-007":
      | result  | retryCount | retrievedBulletIds |
      | SUCCESS | 0           | ["bullet-P"]         |
      | SUCCESS | 1           | ["bullet-P"]         |
      | FAILURE | 0           | ["bullet-P"]         |
    And a PlaybookManager
    And a PlaybookReliabilityAnalyzer initialized with the logger and manager
    When bulletReliability is called with playbookId "playbook-007"
    Then a list with 1 BulletReliability is returned:
      | bulletId | timesRetrieved | firstPassCount | firstPassRate |
      | bullet-P  | 3               | 1                | 0.333333        |