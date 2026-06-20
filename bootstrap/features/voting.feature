Feature: Voting System for Ensemble Learning

  Scenario: Majority voting approves bullet with more than 50% approval
    Given a ConsensusBullet with 3 APPROVE votes and 2 REJECT votes
    And a MajorityVoting strategy
    When the strategy decides on the bullet
    Then the decision is True

  Scenario: Majority voting rejects bullet with 50% or less approval
    Given a ConsensusBullet with 2 APPROVE votes and 2 REJECT votes
    And a MajorityVoting strategy
    When the strategy decides on the bullet
    Then the decision is False

  Scenario: Majority voting rejects bullet with no votes
    Given a ConsensusBullet with 0 APPROVE votes and 0 REJECT votes
    And a MajorityVoting strategy
    When the strategy decides on the bullet
    Then the decision is False

  Scenario: Supermajority voting approves bullet meeting threshold
    Given a ConsensusBullet with 4 APPROVE votes and 2 REJECT votes
    And a SupermajorityVoting strategy with threshold 0.667
    When the strategy decides on the bullet
    Then the decision is True

  Scenario: Supermajority voting rejects bullet below threshold
    Given a ConsensusBullet with 3 APPROVE votes and 2 REJECT votes
    And a SupermajorityVoting strategy with threshold 0.667
    When the strategy decides on the bullet
    Then the decision is False

  Scenario: Weighted voting approves bullet with weighted approval above threshold
    Given a ConsensusBullet with modelA voting APPROVE and modelB voting REJECT
    And modelA has votingWeight 0.8 and modelB has votingWeight 0.2
    And a WeightedVoting strategy with threshold 0.5
    When the strategy decides on the bullet with model performance data
    Then the decision is True

  Scenario: Weighted voting falls back to majority when no performance data provided
    Given a ConsensusBullet with 3 APPROVE votes and 1 REJECT vote
    And a WeightedVoting strategy with threshold 0.5
    When the strategy decides on the bullet without model performance data
    Then the decision is True

  Scenario: Unanimous voting approves only when all votes are APPROVE
    Given a ConsensusBullet with 3 APPROVE votes and 0 REJECT votes
    And a UnanimousVoting strategy
    When the strategy decides on the bullet
    Then the decision is True

  Scenario: Unanimous voting rejects when any REJECT vote exists
    Given a ConsensusBullet with 5 APPROVE votes and 1 REJECT vote
    And a UnanimousVoting strategy
    When the strategy decides on the bullet
    Then the decision is False

  Scenario: Escalating voting uses initial threshold in early rounds
    Given a ConsensusBullet with 3 APPROVE votes and 1 REJECT vote and deliberationRounds 0
    And an EscalatingVoting strategy with initialThreshold 0.75, finalThreshold 0.5, maxRounds 3
    When the strategy decides on the bullet
    Then the decision is True

  Scenario: Escalating voting uses final threshold after max rounds
    Given a ConsensusBullet with 2 APPROVE votes and 2 REJECT votes and deliberationRounds 3
    And an EscalatingVoting strategy with initialThreshold 0.75, finalThreshold 0.5, maxRounds 3
    When the strategy decides on the bullet
    Then the decision is True

  Scenario: VotingSystem separates approved and rejected bullets
    Given a VotingSystem with MajorityVoting strategy
    And a list containing bullet1 with 3 APPROVE and 1 REJECT, bullet2 with 1 APPROVE and 3 REJECT
    When voteOnBullets is called with the bullet list
    Then the approved list contains bullet1
    And the rejected list contains bullet2
    And bullet1 has approved True and approvalStrategy "majority"
    And bullet2 has approved False and approvalStrategy "majority"

  Scenario: VotingSystem rejects bullets with no votes
    Given a VotingSystem with MajorityVoting strategy
    And a ConsensusBullet with no votes
    When voteOnBullets is called with the bullet
    Then the bullet is in the rejected list
    And the bullet has approved False and approvalStrategy "no_votes"

  Scenario: VotingSystem identifies contested bullets within approval range
    Given a VotingSystem with MajorityVoting strategy
    And bullets with approvalRate 0.3, 0.45, 0.55, 0.7
    When getContestedBullets is called with minApproval 0.4 and maxApproval 0.6
    Then the contested list contains bullets with approvalRate 0.45 and 0.55

  Scenario: VotingSystem analyzes disagreement metrics
    Given a VotingSystem with MajorityVoting strategy
    And bullets with approvalRate 0.0, 0.5, 1.0
    When analyzeDisagreement is called with the bullets
    Then the result contains totalBullets 3
    And the result contains unanimous 2
    And the result contains highlyContested 1
    And the result contains avgApprovalRate 0.5
    And the result contains minApprovalRate 0.0
    And the result contains maxApprovalRate 1.0

  Scenario: VotingSystem returns empty dict when analyzing empty bullet list
    Given a VotingSystem with MajorityVoting strategy
    And an empty list of bullets
    When analyzeDisagreement is called with the empty list
    Then the result is an empty dict