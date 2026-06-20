Feature: DBSCAN Clustering for Playbook Bullets

  Scenario: Clustering an empty list of bullets
    Given a BulletClusterer with eps 0.3 and minSamples 2
    When cluster is called with an empty list
    Then the result has 0 clusters
    And the result has 0 outliers
    And the distillationSet is empty

  Scenario: Clustering bullets without embeddings
    Given a BulletClusterer with eps 0.3 and minSamples 2
    And 3 bullets without embeddings
    When cluster is called with these bullets
    Then the result has 0 clusters
    And the result has 3 outliers
    And the distillationSet is empty

  Scenario: Clustering bullets into a single cluster with highest helpful strategy
    Given a BulletClusterer with eps 0.5, minSamples 2, and strategy HIGHEST_HELPFUL
    And 3 bullets with similar embeddings and helpful counts 5, 8, 3 and harmful counts 1, 2, 1
    When cluster is called with these bullets
    Then the result has 1 cluster
    And the result has 0 outliers
    And the distillationSet contains 1 bullet
    And the distillationSet bullet has helpfulCount 8

  Scenario: Clustering bullets into multiple clusters
    Given a BulletClusterer with eps 0.3 and minSamples 2
    And 2 bullets with embeddings [1.0, 0.0, 0.0] and [0.99, 0.1, 0.0]
    And 2 bullets with embeddings [0.0, 1.0, 0.0] and [0.0, 0.99, 0.1]
    When cluster is called with these bullets
    Then the result has 2 clusters
    And the result has 0 outliers
    And the distillationSet contains 2 bullets

  Scenario: Clustering with outliers when minSamples threshold not met
    Given a BulletClusterer with eps 0.3 and minSamples 3
    And 2 bullets with embeddings [1.0, 0.0, 0.0] and [0.99, 0.1, 0.0]
    And 1 bullet with embedding [0.0, 0.0, 1.0]
    When cluster is called with these bullets
    Then the result has 0 clusters
    And the result has 3 outliers
    And the distillationSet is empty

  Scenario: Selecting representative by most central strategy
    Given a BulletClusterer with eps 0.5, minSamples 2, and strategy MOST_CENTRAL
    And 3 bullets with embeddings [1.0, 0.0], [0.9, 0.1], and [0.8, 0.2]
    When cluster is called with these bullets
    Then the distillationSet contains 1 bullet
    And the representative is the bullet closest to the centroid

  Scenario: Selecting representative by most recent strategy
    Given a BulletClusterer with eps 0.5, minSamples 2, and strategy MOST_RECENT
    And 3 bullets with similar embeddings and createdAt timestamps 100, 200, 150
    When cluster is called with these bullets
    Then the distillationSet contains 1 bullet
    And the distillationSet bullet has createdAt 200

  Scenario: Clustering by model strength filters weak models
    Given a BulletClusterer with eps 0.3 and minSamples 2
    And 2 bullets with embeddings [1.0, 0.0] from model "gpt-4o"
    And 2 bullets with embeddings [0.0, 1.0] from model "weak-model"
    And modelWeights {"gpt-4o": 1.5, "weak-model": 0.5}
    When clusterByModelStrength is called with minWeight 1.0
    Then the result has 0 clusters
    And the result has 0 outliers

  Scenario: Finding knowledge gaps between strong and weak models
    Given a BulletClusterer with eps 0.3 and minSamples 2
    And a strongResult with 1 cluster centered at [1.0, 0.0, 0.0]
    And 2 weakBullets with embeddings [0.0, 1.0, 0.0] and [0.99, 0.1, 0.0]
    When findKnowledgeGaps is called
    Then 1 bullet is returned as a gap

  Scenario: Building distillation playbook with model weights
    Given 4 bullets with embeddings from models "strong-1" and "weak-1"
    And modelWeights {"strong-1": 1.5, "weak-1": 0.8}
    When buildDistillationPlaybook is called with minModelWeight 1.0, eps 0.3, minSamples 2
    Then a tuple of distillationBullets and ClusteringResult is returned
    And only bullets from "strong-1" are included in clustering

  Scenario: BulletCluster properties calculate correctly
    Given a BulletCluster with 3 bullets
    And bullets have helpfulCount 4, 6, 2 and harmfulCount 1, 2, 2
    And bullets are from models "model-a", "model-b", "model-a"
    Then the cluster size is 3
    And the avgHelpfulRatio is 0.6666666666666666
    And modelsRepresented contains "model-a" and "model-b"

  Scenario: ClusteringResult coverageByModel tracks model contributions
    Given a ClusteringResult with 2 clusters
    And cluster 0 has bullets from models "model-a" and "model-b"
    And cluster 1 has bullets from models "model-a" and "model-c"
    Then coverageByModel shows "model-a": 2, "model-b": 1, "model-c": 1