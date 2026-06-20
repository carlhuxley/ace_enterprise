Feature: Consensus Building for Ensemble Learning
  Consensus building clusters similar bullets, deduplicates proposals, and analyzes agreement patterns.

  Scenario: Clustering identical bullets into a single cluster
    Given a ConsensusBuilder with similarityThreshold 0.85
    And a ConsensusBullet with content "Increased revenue by 25%" proposedBy "model_a"
    And a ConsensusBullet with content "Increased revenue by 25%" proposedBy "model_b"
    When clusterBullets is called with these bullets
    Then the result contains 1 cluster
    And both bullets are assigned the same clusterId

  Scenario: Clustering similar bullets together
    Given a ConsensusBuilder with similarityThreshold 0.85
    And a ConsensusBullet with content "Led team of 5 engineers" proposedBy "model_a"
    And a ConsensusBullet with content "Managed team of 5 software engineers" proposedBy "model_b"
    And a ConsensusBullet with content "Implemented new payment system" proposedBy "model_c"
    When clusterBullets is called with these bullets
    Then the result contains 2 clusters
    And the first two bullets share the same clusterId
    And the third bullet has a different clusterId

  Scenario: Building consensus from unique bullets
    Given a ConsensusBuilder with similarityThreshold 0.85
    And a ConsensusBullet with content "Reduced costs by 30%" proposedBy "model_a"
    And a ConsensusBullet with content "Launched mobile app" proposedBy "model_b"
    When buildConsensus is called with these bullets
    Then the result contains 2 bullets
    And the first bullet content is "Reduced costs by 30%"
    And the second bullet content is "Launched mobile app"

  Scenario: Building consensus merges similar bullets
    Given a ConsensusBuilder with similarityThreshold 0.85
    And a ConsensusBullet with content "Led team" proposedBy "model_a" with tags ["leadership"]
    And a ConsensusBullet with content "Led team of engineers" proposedBy "model_b" with tags ["management"]
    When buildConsensus is called with these bullets
    Then the result contains 1 bullet
    And the bullet content is "Led team of engineers"
    And the bullet proposedBy starts with "consensus_2"
    And the bullet tags contain both "leadership" and "management"

  Scenario: Calculating diversity score with all unique bullets
    Given a ConsensusBuilder with similarityThreshold 0.85
    And 5 ConsensusBullets with completely different content
    When calculateDiversityScore is called with these bullets
    Then the diversity score is 1.0

  Scenario: Calculating diversity score with duplicate bullets
    Given a ConsensusBuilder with similarityThreshold 0.85
    And 4 ConsensusBullets where 2 pairs are identical
    When calculateDiversityScore is called with these bullets
    Then the diversity score is 0.5

  Scenario: Identifying unique contributions by model
    Given a ConsensusBuilder with similarityThreshold 0.85
    And a ConsensusBullet with content "Unique to model A" proposedBy "model_a"
    And a ConsensusBullet with content "Shared idea" proposedBy "model_a"
    And a ConsensusBullet with content "Shared idea similar" proposedBy "model_b"
    And a ConsensusBullet with content "Unique to model B" proposedBy "model_b"
    When getUniqueContributions is called with these bullets
    Then the result for "model_a" contains 1 bullet with content "Unique to model A"
    And the result for "model_b" contains 1 bullet with content "Unique to model B"

  Scenario: Calculating consensus strength from voted bullets
    Given a ConsensusBuilder with similarityThreshold 0.85
    And a ConsensusBullet with votes resulting in approvalRate 0.9
    And a ConsensusBullet with votes resulting in approvalRate 0.85
    And a ConsensusBullet with votes resulting in approvalRate 0.95
    When calculateConsensusStrength is called with these bullets
    Then the consensus strength is greater than 0.8

  Scenario: Calculating agreement matrix between models
    Given a ConsensusBuilder with similarityThreshold 0.85
    And a ConsensusBullet with a vote "approve" from "model_a" and vote "approve" from "model_b"
    And a ConsensusBullet with a vote "approve" from "model_a" and vote "reject" from "model_b"
    When getAgreementMatrix is called with these bullets
    Then the result contains key ("model_a", "model_b") with value 0.5