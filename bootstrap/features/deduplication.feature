Feature: Bullet Deduplication

  Scenario: Check duplicate bullets with embeddings above similarity threshold
    Given a BulletDeduplicator with similarityThreshold 0.85
    And a bullet with content "Implement user authentication" and embedding [1.0, 0.0, 0.0] and helpfulCount 5 and harmfulCount 1
    And a bullet with content "Add user authentication feature" and embedding [0.9, 0.1, 0.0] and helpfulCount 3 and harmfulCount 2
    When isDuplicate is called with both bullets
    Then the result is True

  Scenario: Check non-duplicate bullets with embeddings below similarity threshold
    Given a BulletDeduplicator with similarityThreshold 0.85
    And a bullet with content "Implement user authentication" and embedding [1.0, 0.0, 0.0] and helpfulCount 5 and harmfulCount 1
    And a bullet with content "Fix database connection" and embedding [0.0, 1.0, 0.0] and helpfulCount 3 and harmfulCount 2
    When isDuplicate is called with both bullets
    Then the result is False

  Scenario: Check bullets without embeddings using exact match
    Given a BulletDeduplicator with similarityThreshold 0.85
    And a bullet with content "Implement feature" and embedding None and helpfulCount 5 and harmfulCount 1
    And a bullet with content "  IMPLEMENT FEATURE  " and embedding None and helpfulCount 3 and harmfulCount 2
    When isDuplicate is called with both bullets
    Then the result is True

  Scenario: Find all duplicate pairs in a list of bullets
    Given a BulletDeduplicator with similarityThreshold 0.90
    And a list of bullets with embeddings [[1.0, 0.0], [0.95, 0.05], [0.0, 1.0], [0.96, 0.04]]
    When findDuplicates is called with the bullet list
    Then the result contains tuple (0, 1, 0.9987) approximately
    And the result contains tuple (0, 3, 0.9992) approximately
    And the result contains tuple (1, 3, 0.9999) approximately
    And the result has length 3

  Scenario: Deduplicate bullets preserving highest helpful ratio
    Given a BulletDeduplicator with similarityThreshold 0.90
    And a bullet at index 0 with content "Feature A" and embedding [1.0, 0.0] and helpfulCount 8 and harmfulCount 2
    And a bullet at index 1 with content "Feature B" and embedding [0.95, 0.05] and helpfulCount 5 and harmfulCount 5
    And a bullet at index 2 with content "Feature C" and embedding [0.0, 1.0] and helpfulCount 3 and harmfulCount 1
    When deduplicate is called with preserveStrategy "highestRatio"
    Then the result has length 2
    And the result contains the bullet at original index 0
    And the result contains the bullet at original index 2

  Scenario: Deduplicate bullets preserving most recent
    Given a BulletDeduplicator with similarityThreshold 0.90
    And a bullet with content "Feature A" and embedding [1.0, 0.0] and createdAt "2024-01-01T10:00:00"
    And a bullet with content "Feature B" and embedding [0.95, 0.05] and createdAt "2024-01-02T10:00:00"
    When deduplicate is called with preserveStrategy "mostRecent"
    Then the result has length 1
    And the result contains the bullet with createdAt "2024-01-02T10:00:00"

  Scenario: Deduplicate bullets preserving most used
    Given a BulletDeduplicator with similarityThreshold 0.90
    And a bullet with content "Feature A" and embedding [1.0, 0.0] and helpfulCount 3 and harmfulCount 2
    And a bullet with content "Feature B" and embedding [0.95, 0.05] and helpfulCount 5 and harmfulCount 3
    When deduplicate is called with preserveStrategy "mostUsed"
    Then the result has length 1
    And the result contains the bullet with helpfulCount 5 and harmfulCount 3

  Scenario: Group bullets into duplicate clusters
    Given a BulletDeduplicator with similarityThreshold 0.90
    And a list of 5 bullets where bullets 0, 1, 3 have similar embeddings and bullets 2, 4 are unique
    When getDuplicateGroups is called
    Then the result contains a group with indices [0, 1, 3]
    And the result has length 1

  Scenario: Deduplicate empty list returns empty list
    Given a BulletDeduplicator with similarityThreshold 0.85
    And an empty list of bullets
    When deduplicate is called with preserveStrategy "highestRatio"
    Then the result is an empty list
