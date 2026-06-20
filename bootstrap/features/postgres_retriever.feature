Feature: PostgreSQL Bullet Retriever

  Scenario: Initialize retriever with default settings
    Given a PostgresPlaybookAdapter instance
    When I create a PostgresBulletRetriever with the adapter
    Then the retriever should use default topK from settings
    And the retriever should use default similarityThreshold from settings

  Scenario: Initialize retriever with custom parameters
    Given a PostgresPlaybookAdapter instance
    When I create a PostgresBulletRetriever with topK 15 and similarityThreshold 0.8
    Then the retriever should use topK 15
    And the retriever should use similarityThreshold 0.8

  Scenario: Retrieve bullets with basic query
    Given a PostgresBulletRetriever instance
    When I call retrieve with query "implement authentication"
    Then I should receive a list of bullet and score tuples
    And each tuple should contain a Bullet object and a float score
    And the results should be sorted by relevance score descending

  Scenario: Retrieve bullets filtered by playbook
    Given a PostgresBulletRetriever instance
    When I call retrieve with query "error handling" and playbookId "playbook-123"
    Then I should receive bullets only from playbook "playbook-123"
    And each result should be a tuple of Bullet and float score

  Scenario: Retrieve bullets filtered by section
    Given a PostgresBulletRetriever instance
    When I call retrieve with query "testing" and filterSection "quality_assurance"
    Then I should receive only bullets where section equals "quality_assurance"
    And each result should be a tuple of Bullet and float score

  Scenario: Retrieve bullets filtered by minimum confidence score
    Given a PostgresBulletRetriever instance
    When I call retrieve with query "deployment" and minConfidence 0.7
    Then I should receive only bullets with confidenceScore greater than or equal to 0.7
    And each result should be a tuple of Bullet and float score

  Scenario: Retrieve bullets filtered by domain
    Given a PostgresBulletRetriever instance
    When I call retrieve with query "optimization" and domain "backend"
    Then I should receive only bullets where applicableDomains is None or contains "backend"
    And each result should be a tuple of Bullet and float score

  Scenario: Retrieve bullets filtered by project
    Given a PostgresBulletRetriever instance
    When I call retrieve with query "refactoring" and projectId "proj-456"
    Then I should receive only bullets where projectIds is None or contains "proj-456"
    And each result should be a tuple of Bullet and float score

  Scenario: Retrieve bullets filtered by helpful ratio
    Given a PostgresBulletRetriever instance
    When I call retrieve with query "code review" and minHelpfulRatio 0.75
    Then I should receive only bullets where helpfulCount divided by total feedback is at least 0.75
    And each result should be a tuple of Bullet and float score

  Scenario: Retrieve bullets with custom topK override
    Given a PostgresBulletRetriever instance with default topK 10
    When I call retrieve with query "security" and topK 5
    Then I should receive at most 5 bullet and score tuples

  Scenario: Retrieve from bullets list for backwards compatibility
    Given a PostgresBulletRetriever instance
    And a list of Bullet objects
    When I call retrieveFromBullets with query "performance" and the bullet list
    Then I should receive a list of bullet and score tuples
    And the results should be sorted by relevance score descending

  Scenario: Retrieve cross-model with primary playbook
    Given a PostgresBulletRetriever instance
    When I call retrieveCrossModel with query "database design" and primaryPlaybookId "primary-123"
    Then I should receive a list of tuples containing Bullet, float score, and source playbook ID
    And bullets from "primary-123" should have unmodified scores
    And bullets from other playbooks should have scores multiplied by secondaryWeight

  Scenario: Retrieve cross-model with custom secondary weight
    Given a PostgresBulletRetriever instance
    When I call retrieveCrossModel with query "API design", primaryPlaybookId "primary-123", and secondaryWeight 0.3
    Then bullets from playbooks other than "primary-123" should have scores multiplied by 0.3
    And the results should be sorted by adjusted score descending
    And I should receive at most topK results

  Scenario: Retrieve cross-model filtered by confidence
    Given a PostgresBulletRetriever instance
    When I call retrieveCrossModel with query "caching" and minConfidence 0.8
    Then I should receive only bullets with confidenceScore greater than or equal to 0.8
    And each result should be a tuple of Bullet, float score, and string playbook ID

  Scenario: Retrieve cross-model filtered by domain
    Given a PostgresBulletRetriever instance
    When I call retrieveCrossModel with query "monitoring" and domain "devops"
    Then I should receive only bullets where applicableDomains is None or contains "devops"
    And each result should include the source playbook ID

  Scenario: Retrieve cross-model filtered by project
    Given a PostgresBulletRetriever instance
    When I call retrieveCrossModel with query "migration" and projectId "proj-789"
    Then I should receive only bullets where projectIds is None or contains "proj-789"
    And each result should be a tuple of Bullet, float score, and string playbook ID