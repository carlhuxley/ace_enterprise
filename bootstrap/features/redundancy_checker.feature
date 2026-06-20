Feature: Redundancy Pre-Checker
  As a test developer
  I want to detect redundant tests before writing them
  So that I avoid duplicate test coverage

  Scenario: No existing tests means proposed test is not redundant
    Given no existing tests
    When I check a proposed test named "test_add_numbers" with description "Tests addition of two numbers"
    Then the result should indicate not redundant
    And the reason should be "No existing tests to conflict with"
    And the confidence should be 1.0

  Scenario: Exact name match indicates definite redundancy
    Given an existing test named "test_calculate_sum" with assertions ["assert result == 5"] in file "test_math.py"
    When I check a proposed test named "test_calculate_sum" with description "Adds two numbers together"
    Then the result should indicate redundant
    And the reason should be "Duplicate test name: 'test_calculate_sum' already exists"
    And the confidence should be 1.0

  Scenario: Edge case test is not redundant even if base operation exists
    Given an existing test named "test_add_numbers" with assertions ["assert add(2, 3) == 5"] in file "test_math.py"
    When I check a proposed test named "test_add_negative_numbers" with description "Tests addition with negative values"
    Then the result should indicate not redundant
    And the reason should contain "Tests edge case: negative"
    And the confidence should be 0.9

  Scenario: Same operation on same subject indicates redundancy
    Given an existing test named "test_add_plant" with assertions ["assert garden.add(plant)"] in file "test_garden.py"
    When I check a proposed test named "test_sum_plant" with description "Tests adding a plant to collection"
    Then the result should indicate redundant
    And the reason should be "Tests same behavior: add already tested in test_add_plant"
    And the confidence should be 0.8

  Scenario: Same operation on different subjects is not redundant
    Given an existing test named "test_add_plant" with assertions ["assert garden.add(plant)"] in file "test_garden.py"
    When I check a proposed test named "test_add_building" with description "Tests adding a building to city"
    Then the result should indicate not redundant
    And the reason should be "Proposed test covers new behavior"
    And the confidence should be 0.85

  Scenario: Proposed test implicitly covered by broader existing test
    Given an existing test named "test_calculator_operations" with assertions ["result = calculator.multiply(3, 4)", "assert result == 12"] in file "test_calc.py"
    When I check a proposed test named "test_multiply" with description "Tests multiplication"
    Then the result should indicate redundant
    And the reason should be "Already covered by broader test: test_calculator_operations"
    And the confidence should be 0.75

  Scenario: Multiple edge case indicators prevent redundancy detection
    Given an existing test named "test_divide_numbers" with assertions ["assert divide(10, 2) == 5"] in file "test_math.py"
    When I check a proposed test named "test_divide_by_zero_error" with description "Tests division by zero raises exception"
    Then the result should indicate not redundant
    And the reason should contain "Tests edge case:"
    And the confidence should be 0.9

  Scenario: Synonym operations on same subject detected as redundant
    Given an existing test named "test_creation_of_user" with assertions ["assert User.create(name)"] in file "test_user.py"
    When I check a proposed test named "test_instantiate_user" with description "Tests user instantiation"
    Then the result should indicate redundant
    And the reason should be "Tests same behavior: create already tested in test_creation_of_user"
    And the confidence should be 0.8