Feature: Ensemble voting strategies for consensus bullets

  Scenario: Majority voting approves a bullet with more than 50% approval
    Given a bullet with 3 APPROVE votes and 2 REJECT votes
    When the majority voting strategy decides on the bullet
    Then the bullet is approved

  Scenario: Majority voting rejects a bullet with no votes
    Given a bullet with no votes
    When the voting system votes on a list containing that bullet
    Then the bullet is rejected with approval strategy "no_votes"

  Scenario: Supermajority voting requires at least two-thirds approval
    Given a bullet with 2 APPROVE votes and 1 REJECT vote
    When the supermajority voting strategy decides on the bullet
    Then the bullet is rejected

  Scenario: Weighted voting approves based on model accuracy weights rather than vote count
    Given a bullet with 1 APPROVE vote from model "high_accuracy_model" and 2 REJECT votes from lower-weight models
    And model performance data giving "high_accuracy_model" a voting weight of 5.0 and the other models a voting weight of 1.0 each
    When the weighted voting strategy decides on the bullet using that performance data
    Then the bullet is approved

  Scenario: Weighted voting falls back to majority voting when no performance data is supplied
    Given a bullet with 3 APPROVE votes and 1 REJECT vote
    When the weighted voting strategy decides on the bullet without any model performance data
    Then the bullet is approved

  Scenario: Unanimous voting rejects a bullet with even a single rejection
    Given a bullet with 4 APPROVE votes and 1 REJECT vote
    When the unanimous voting strategy decides on the bullet
    Then the bullet is rejected

  Scenario: Voting system separates bullets into approved and rejected lists
    Given a list of bullets where one has majority approval and another has majority rejection
    When the voting system votes on all bullets using the majority strategy
    Then the approved list contains the majority-approved bullet
    And the rejected list contains the majority-rejected bullet

  Scenario: Identifying contested bullets by approval rate range
    Given bullets with approval rates of 0.3, 0.5, and 0.9
    When the voting system searches for contested bullets between 0.4 and 0.6 approval
    Then only the bullet with an approval rate of 0.5 is returned as contested

  Scenario: Analyzing disagreement statistics across bullets
    Given bullets with approval rates of 0.0, 0.5, and 1.0
    When the voting system analyzes disagreement across those bullets
    Then the statistics report 2 unanimous bullets and 1 highly contested bullet
    And the average approval rate is 0.5