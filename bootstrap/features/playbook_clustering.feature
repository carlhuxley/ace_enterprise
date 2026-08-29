Feature: DBSCAN clustering of playbook bullets for prompt-level distillation

  As a caller building a distillation playbook from accumulated bullets,
  I want bullets grouped by semantic similarity into clusters with a
  chosen representative per cluster, so I can produce a diverse,
  high-quality set of bullets for injection into model prompts.

  Scenario: Clustering an empty list of bullets returns an empty result
    Given no bullets are provided
    When I cluster the bullets with eps 0.3 and min_samples 2
    Then the result has 0 clusters and 0 outliers
    And the distillation set is empty

  Scenario: Bullets without embeddings are treated as outliers
    Given bullet "b1" has no embedding
    And bullet "b2" has no embedding
    When I cluster the bullets with eps 0.3 and min_samples 2
    Then the result has 0 clusters
    And the outliers include "b1" and "b2"
    And the distillation set is empty

  Scenario: Semantically similar bullets are grouped into a cluster with a representative
    Given bullet "b1" has embedding [1.0, 0.0, 0.0], 8 helpful votes and 2 harmful votes
    And bullet "b2" has embedding [0.99, 0.01, 0.0], 3 helpful votes and 7 harmful votes
    When I cluster the bullets with eps 0.3 and min_samples 2 using the "highest_helpful" strategy
    Then the result has 1 cluster containing "b1" and "b2"
    And the cluster representative is "b1"
    And the distillation set contains exactly "b1"

  Scenario: A bullet with no near neighbors is reported as an outlier, not a cluster
    Given bullet "b1" has embedding [1.0, 0.0, 0.0]
    And bullet "b2" has embedding [0.0, 1.0, 0.0]
    When I cluster the bullets with eps 0.3 and min_samples 2
    Then the result has 0 clusters
    And the outliers include "b1" and "b2"

  Scenario: Selecting the most recent bullet as cluster representative
    Given bullet "b1" has embedding [1.0, 0.0, 0.0] and was created on "2026-01-01"
    And bullet "b2" has embedding [0.99, 0.01, 0.0] and was created on "2026-06-01"
    When I cluster the bullets with eps 0.3 and min_samples 2 using the "most_recent" strategy
    Then the cluster representative is "b2"

  Scenario: Filtering bullets by model strength excludes weak models before clustering
    Given bullet "b1" was created by model "gpt-4o" with embedding [1.0, 0.0, 0.0]
    And bullet "b2" was created by model "qwen2.5-7b" with embedding [0.99, 0.01, 0.0]
    And the model weights are {"gpt-4o": 1.8, "qwen2.5-7b": 0.8}
    When I cluster by model strength with minimum weight 1.0
    Then the result only considers bullets from "gpt-4o"
    And "b2" does not appear in any cluster or as an outlier from this call

  Scenario: Finding knowledge gaps between weak and strong model bullets
    Given a strong-model clustering result has one cluster centered near embedding [1.0, 0.0, 0.0] with eps 0.3
    And weak bullet "w1" has embedding [1.0, 0.0, 0.0]
    And weak bullet "w2" has embedding [0.0, 0.0, 1.0]
    When I find knowledge gaps between the strong result and the weak bullets
    Then the knowledge gaps contain "w2"
    And the knowledge gaps do not contain "w1"

  Scenario: Building a distillation playbook filters by model weight and returns representative bullets
    Given bullet "b1" was created by model "claude-3-opus" with embedding [1.0, 0.0, 0.0], 9 helpful votes and 1 harmful vote
    And bullet "b2" was created by model "qwen2.5-7b" with embedding [0.98, 0.02, 0.0], 9 helpful votes and 1 harmful vote
    And the model weights are {"claude-3-opus": 1.7, "qwen2.5-7b": 0.8}
    When I build a distillation playbook with minimum model weight 1.0
    Then the returned distillation bullets contain "b1"
    And the returned distillation bullets do not contain "b2"