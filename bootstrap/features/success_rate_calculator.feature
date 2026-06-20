Feature: Success Rate Calculator
  Calculates experiment success rates across different dimensions

  Scenario: Calculate overall success rate with no experiments
    Given an experiment logger with no records
    When I calculate the overall rate
    Then the success rate is 0.0

  Scenario: Calculate overall success rate with mixed results
    Given an experiment logger with records:
      | experimentType | result  | playbookVersion | timestamp           |
      | typeA           | SUCCESS | v1.0             | 2024-01-15 10:00:00 |
      | typeA           | FAILURE | v1.0             | 2024-01-15 11:00:00 |
      | typeB           | SUCCESS | v1.1             | 2024-01-15 12:00:00 |
      | typeB           | SUCCESS | v1.1             | 2024-01-15 13:00:00 |
    When I calculate the overall rate
    Then the success rate is 0.75

  Scenario: Calculate overall success rate filtered by experiment type
    Given an experiment logger with records:
      | experimentType | result  | playbookVersion | timestamp           |
      | typeA           | SUCCESS | v1.0             | 2024-01-15 10:00:00 |
      | typeA           | FAILURE | v1.0             | 2024-01-15 11:00:00 |
      | typeB           | SUCCESS | v1.1             | 2024-01-15 12:00:00 |
      | typeB           | SUCCESS | v1.1             | 2024-01-15 13:00:00 |
    When I calculate the overall rate for experiment type "typeA"
    Then the success rate is 0.5

  Scenario: Calculate overall success rate filtered by time
    Given an experiment logger with records:
      | experimentType | result  | playbookVersion | timestamp           |
      | typeA           | FAILURE | v1.0             | 2024-01-10 10:00:00 |
      | typeA           | SUCCESS | v1.0             | 2024-01-15 11:00:00 |
      | typeA           | SUCCESS | v1.1             | 2024-01-15 12:00:00 |
    When I calculate the overall rate since "2024-01-14 00:00:00"
    Then the success rate is 1.0

  Scenario: Calculate success rate by experiment type
    Given an experiment logger with records:
      | experimentType | result  | playbookVersion | timestamp           |
      | typeA           | SUCCESS | v1.0             | 2024-01-15 10:00:00 |
      | typeA           | FAILURE | v1.0             | 2024-01-15 11:00:00 |
      | typeB           | SUCCESS | v1.1             | 2024-01-15 12:00:00 |
      | typeB           | SUCCESS | v1.1             | 2024-01-15 13:00:00 |
      | typeC           | FAILURE | v1.2             | 2024-01-15 14:00:00 |
    When I calculate the rate by type
    Then the rates by type are:
      | experimentType | successRate |
      | typeA           | 0.5          |
      | typeB           | 1.0          |
      | typeC           | 0.0          |

  Scenario: Calculate success rate by playbook version sorted newest first
    Given an experiment logger with records:
      | experimentType | result  | playbookVersion | timestamp           |
      | typeA           | SUCCESS | v1.0             | 2024-01-15 10:00:00 |
      | typeA           | FAILURE | v1.0             | 2024-01-15 11:00:00 |
      | typeA           | SUCCESS | v2.0             | 2024-01-15 12:00:00 |
      | typeA           | SUCCESS | v2.0             | 2024-01-15 13:00:00 |
      | typeA           | SUCCESS | v2.0             | 2024-01-15 14:00:00 |
    When I calculate the rate by playbook version
    Then the version rates are ordered:
      | playbookVersion | total | successCount | successRate |
      | v2.0             | 3     | 3             | 1.0          |
      | v1.0             | 2     | 1             | 0.5          |

  Scenario: Calculate success rate by playbook version filtered by experiment type
    Given an experiment logger with records:
      | experimentType | result  | playbookVersion | timestamp           |
      | typeA           | SUCCESS | v1.0             | 2024-01-15 10:00:00 |
      | typeA           | FAILURE | v1.0             | 2024-01-15 11:00:00 |
      | typeB           | SUCCESS | v1.0             | 2024-01-15 12:00:00 |
      | typeB           | SUCCESS | v2.0             | 2024-01-15 13:00:00 |
    When I calculate the rate by playbook version for experiment type "typeA"
    Then the version rates are ordered:
      | playbookVersion | total | successCount | successRate |
      | v1.0             | 2     | 1             | 0.5          |

  Scenario: Calculate trend over time periods with default parameters
    Given the current time is "2024-01-22 00:00:00"
    And an experiment logger with records:
      | experimentType | result  | playbookVersion | timestamp           |
      | typeA           | SUCCESS | v1.0             | 2024-01-08 10:00:00 |
      | typeA           | FAILURE | v1.0             | 2024-01-09 11:00:00 |
      | typeA           | SUCCESS | v1.0             | 2024-01-16 12:00:00 |
      | typeA           | SUCCESS | v1.0             | 2024-01-17 13:00:00 |
      | typeA           | SUCCESS | v1.0             | 2024-01-18 14:00:00 |
    When I calculate the trend with 10 periods of 7 days
    Then the trend periods are ordered oldest first with non-empty periods:
      | periodStart        | periodEnd          | total | successCount | successRate |
      | 2024-01-08 00:00:00 | 2024-01-15 00:00:00 | 2     | 1             | 0.5          |
      | 2024-01-15 00:00:00 | 2024-01-22 00:00:00 | 3     | 3             | 1.0          |

  Scenario: Calculate trend filtered by experiment type
    Given the current time is "2024-01-22 00:00:00"
    And an experiment logger with records:
      | experimentType | result  | playbookVersion | timestamp           |
      | typeA           | SUCCESS | v1.0             | 2024-01-16 10:00:00 |
      | typeA           | FAILURE | v1.0             | 2024-01-17 11:00:00 |
      | typeB           | SUCCESS | v1.0             | 2024-01-16 12:00:00 |
      | typeB           | SUCCESS | v1.0             | 2024-01-17 13:00:00 |
    When I calculate the trend for experiment type "typeA" with 10 periods of 7 days
    Then the trend periods contain only typeA results:
      | periodStart        | periodEnd          | total | successCount | successRate |
      | 2024-01-15 00:00:00 | 2024-01-22 00:00:00 | 2     | 1             | 0.5          |