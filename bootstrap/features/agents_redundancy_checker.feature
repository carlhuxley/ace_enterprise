Feature: Redundancy Pre-Check for Proposed Tests

  Scenario: No existing tests means proposed test is never redundant
    Given no existing tests
    And a proposed test named "test_add_plant" with description "adds a plant to inventory"
    When the redundancy check is run
    Then the result is not redundant
    And the reason is "No existing tests to conflict with"
    And the confidence is 1.0

  Scenario: Exact name match is flagged as redundant
    Given an existing test named "test_add_plant" with assertions ["assert add(plant) == True"]
    And a proposed test named "test_add_plant" with description "adds a plant to inventory"
    When the redundancy check is run
    Then the result is redundant
    And the reason is "Duplicate test name: 'test_add_plant' already exists"
    And the confidence is 1.0

  Scenario: Same operation and same subject is flagged as redundant
    Given an existing test named "test_add_plant" with assertions ["assert inventory.add(plant) is not None"]
    And a proposed test named "test_add_plant_twice" with description "test that plant can be added to inventory"
    When the redundancy check is run
    Then the result is redundant
    And the reason mentions "Tests same behavior"
    And the confidence is 0.8

  Scenario: Same operation but different subject is not redundant
    Given an existing test named "test_add_plant" with assertions ["assert inventory.add(plant) is not None"]
    And a proposed test named "test_add_structural_asset" with description "test that structural_asset can be added"
    When the redundancy check is run
    Then the result is not redundant
    And the reason is "Proposed test covers new behavior"
    And the confidence is 0.85

  Scenario: Proposed test with an edge case indicator is treated as valuable and not redundant
    Given an existing test named "test_add_plant" with assertions ["assert inventory.add(plant) is not None"]
    And a proposed test named "test_add_plant_negative_quantity" with description "test add with negative quantity raises error"
    When the redundancy check is run
    Then the result is not redundant
    And the reason mentions "Tests edge case"
    And the confidence is 0.9

  Scenario: Proposed test implicitly covered by a broader existing test's assertions
    Given an existing test named "test_calculator_operations" with assertions ["assert calculator.subtract(5, 3) == 2"]
    And a proposed test named "test_subtract_numbers" with description "verifies subtraction works"
    When the redundancy check is run
    Then the result is redundant
    And the reason mentions "Already covered by broader test"
    And the confidence is 0.75

  Scenario: Scanning a non-existent test file returns no existing tests
    Given a test file path that does not exist on disk
    When existing tests are loaded from the file
    Then an empty list of existing tests is returned

  Scenario: Scanning a test file extracts test functions and their assertion lines
    Given a test file containing:
      """
      def test_multiply_numbers():
          result = multiply(2, 3)
          assert result == 6
      """
    When existing tests are loaded from the file
    Then one existing test is returned with name "test_multiply_numbers"
    And its assertions include "assert result == 6"