Feature: Playbook Bullet Reliability Analysis
  As a caller analyzing playbook performance
  I want to see which bullets correlate with first-pass GREEN success
  So that I can identify reliable vs unreliable playbook content

  Scenario: Bullet retrieved across multiple cycles with mixed outcomes
    Given playbook "pb-1" has TDD cycle records where bullet "b-100" was retrieved in 4 cycles
    And 3 of those cycles resulted in "SUCCESS" with retry_count 0
    And 1 of those cycles resulted in "FAILURE"
    When I request bullet reliability for playbook "pb-1"
    Then the result includes a bullet "b-100" with times_retrieved 4
    And first_pass_count 3
    And first_pass_rate 0.75

  Scenario: Bullet with no retrievals is excluded from results
    Given playbook "pb-2" has TDD cycle records where bullet "b-200" is never present in any retrieved_bullet_ids
    When I request bullet reliability for playbook "pb-2"
    Then the result does not include a bullet "b-200"

  Scenario: Results are sorted by first_pass_rate descending
    Given playbook "pb-3" has bullet "b-low" with first_pass_rate 0.2
    And bullet "b-high" with first_pass_rate 0.9
    And bullet "b-mid" with first_pass_rate 0.5
    When I request bullet reliability for playbook "pb-3"
    Then the results are ordered "b-high", "b-mid", "b-low"

  Scenario: Bullet retrieved but never achieving first-pass success has a zero rate
    Given playbook "pb-4" has bullet "b-300" retrieved in 2 cycles
    And both cycles resulted in "FAILURE"
    When I request bullet reliability for playbook "pb-4"
    Then the result includes a bullet "b-300" with times_retrieved 2
    And first_pass_count 0
    And first_pass_rate 0.0

  Scenario: A successful cycle with retries does not count as first-pass
    Given playbook "pb-5" has bullet "b-400" retrieved in 1 cycle
    And that cycle resulted in "SUCCESS" with retry_count 2
    When I request bullet reliability for playbook "pb-5"
    Then the result includes a bullet "b-400" with first_pass_count 0
    And first_pass_rate 0.0

  Scenario: A cycle with no first-pass success where the bullet is retrieved exactly once and succeeds
    Given playbook "pb-6" has bullet "b-500" retrieved in 1 cycle
    And that cycle resulted in "SUCCESS" with retry_count 0
    When I request bullet reliability for playbook "pb-6"
    Then the result includes a bullet "b-500" with times_retrieved 1
    And first_pass_count 1
    And first_pass_rate 1.0

  Scenario: Playbook with no TDD cycle records returns an empty result
    Given playbook "pb-7" has no TDD cycle records
    When I request bullet reliability for playbook "pb-7"
    Then the result is an empty list