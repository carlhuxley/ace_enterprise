Feature: Semantic Deduplication of Playbook Bullets

  Scenario: Bullets with highly similar embeddings are detected as duplicates
    Given a bullet "Always validate user input before processing" with embedding vector [1.0, 0.0, 0.0]
    And a bullet "Always validate user input before processing it" with embedding vector [0.99, 0.01, 0.0]
    When checking if the two bullets are duplicates with similarity threshold 0.85
    Then the result is true

  Scenario: Bullets with dissimilar embeddings are not duplicates
    Given a bullet "Use retries for network calls" with embedding vector [1.0, 0.0, 0.0]
    And a bullet "Log all errors to a file" with embedding vector [0.0, 1.0, 0.0]
    When checking if the two bullets are duplicates with similarity threshold 0.85
    Then the result is false

  Scenario: Bullets without embeddings fall back to case-insensitive exact match
    Given a bullet "Retry failed requests" with no embedding
    And a bullet "retry failed requests" with no embedding
    When checking if the two bullets are duplicates
    Then the result is true

  Scenario: Finding all duplicate pairs in a list of bullets
    Given a list of 3 bullets where bullets at index 0 and 2 have near-identical embeddings and bullet at index 1 is unrelated
    When finding duplicates in the list
    Then the result includes a pair matching indices 0 and 2 with a similarity score
    And no pair includes index 1

  Scenario: Deduplicating keeps the bullet with the highest helpful ratio by default
    Given a bullet "Escalate to human review on failure" with helpful_count 10 and harmful_count 0
    And a duplicate bullet "Escalate to human review on failure." with helpful_count 2 and harmful_count 8
    When deduplicating the list of bullets
    Then the returned list contains only the bullet with helpful_count 10 and harmful_count 0

  Scenario: Deduplicating with "most_recent" strategy keeps the newest bullet
    Given a bullet "Check API rate limits before batch requests" created at "2026-01-01T00:00:00Z"
    And a duplicate bullet "Check API rate limits before batch requests" created at "2026-06-01T00:00:00Z"
    When deduplicating the list of bullets with preserve_strategy "most_recent"
    Then the returned list contains only the bullet created at "2026-06-01T00:00:00Z"

  Scenario: Deduplicating an empty list returns an empty list
    Given an empty list of bullets
    When deduplicating the list of bullets
    Then the returned list is empty

  Scenario: Grouping bullets into duplicate clusters
    Given a list of 4 bullets where indices 0, 1, and 2 are mutual duplicates and index 3 is unique
    When getting duplicate groups for the list
    Then one group contains indices 0, 1, and 2
    And no group contains index 3