Feature: Ensemble consensus building

  Background:
    Given a ConsensusBuilder with similarity_threshold 0.85

  Scenario: Clustering an empty list of bullets returns no clusters
    When I cluster an empty list of bullets
    Then the result is an empty mapping of cluster ids to bullets

  Scenario: Clustering bullets that are all distinct produces one cluster per bullet
    Given bullets "Always validate user input", "Cache database queries", "Use structured logging" proposed by "modelA", "modelB", "modelC" respectively, each pair having similarity below 0.85
    When I cluster the bullets
    Then the result contains 3 clusters
    And each cluster contains exactly one bullet

  Scenario: Clustering near-duplicate bullets groups them into a single cluster
    Given bullets "Always validate all user input before processing" from "modelA" and "Validate all user input before processing" from "modelB", with similarity 0.95 between them
    When I cluster the bullets
    Then the result contains 1 cluster
    And that cluster contains both bullets

  Scenario: Building consensus keeps a unique bullet unchanged
    Given a single bullet "Use structured logging" proposed by "modelC" with no similar bullets
    When I build consensus from the bullets
    Then the consensus list contains 1 bullet
    And that bullet's content is "Use structured logging"
    And that bullet's proposed_by is "modelC"

  Scenario: Building consensus merges near-duplicate bullets into one representative
    Given bullet "Validate input" proposed by "modelA" with tags "security"
    And bullet "Always validate all user input thoroughly" proposed by "modelB" with tags "input-handling"
    And these two bullets have similarity 0.95
    When I build consensus from the bullets
    Then the consensus list contains 1 bullet
    And that bullet's content is "Always validate all user input thoroughly"
    And that bullet's proposed_by is "consensus_2"
    And that bullet's tags include "security" and "input-handling"
    And that bullet's proposal_reasoning mentions "Merged from 2 similar proposals"

  Scenario: Diversity score is 1.0 when every proposal is unique
    Given 3 bullets that are all mutually dissimilar
    When I calculate the diversity score for the bullets
    Then the diversity score is 1.0

  Scenario: Diversity score decreases when proposals are redundant
    Given 4 bullets where 2 of them are near-duplicates of each other and the other 2 are unique
    When I calculate the diversity score for the bullets
    Then the diversity score is 0.75

  Scenario: Consensus strength is zero for an empty list of bullets
    When I calculate the consensus strength for an empty list of bullets
    Then the consensus strength is 0.0

  Scenario: Consensus strength is high when approval rates are uniformly high
    Given bullets that each have an approval_rate of 0.9 with no variance between them
    When I calculate the consensus strength for the bullets
    Then the consensus strength is close to 0.9

  Scenario: Unique contributions only include bullets from single-member clusters
    Given bullet "Use structured logging" proposed by "modelC" with no similar bullets
    And bullets "Validate input" proposed by "modelA" and "Always validate all user input thoroughly" proposed by "modelB" with similarity 0.95 between them
    When I get the unique contributions for the bullets
    Then the result maps "modelC" to a list containing "Use structured logging"
    And the result does not include "modelA" or "modelB"

  Scenario: Agreement matrix reports pairwise agreement rate between models that both voted
    Given a bullet proposed by "modelA" with a vote "approve" from "modelA" and a vote "approve" from "modelB"
    And another bullet proposed by "modelA" with a vote "reject" from "modelA" and a vote "approve" from "modelB"
    When I get the agreement matrix for the bullets
    Then the agreement rate for the pair "modelA" and "modelB" is 0.5