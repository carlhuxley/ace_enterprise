Feature: Test Review Agent
  Analyses test files and produces quality scores and improvement suggestions

  Scenario: Review test file with no test functions scores zero
    Given a test file containing no functions starting with "test_"
    When the test file is reviewed
    Then the overall score is 0.0
    And the review contains a critical issue about no test functions found
    And the test count is 0

  Scenario: Review test function with no assertions produces critical issue
    Given a test file with a function "test_example" that has no assert statements
    When the test file is reviewed
    Then the review contains a critical issue for "test_example"
    And the test count is 1

  Scenario: Review valid test with assertions produces positive score
    Given a test file with a function "test_addition" that has 2 assert statements
    When the test file is reviewed
    Then the test count is 1
    And the overall score is greater than 0.0

  Scenario: Review test with vague name produces a warning
    Given a test file with a function "test_basic" that has 1 assert statement
    When the test file is reviewed
    Then the review contains a warning about the vague name "test_basic"

  Scenario: Review test with excessive assertions produces a warning
    Given a test file with a function "test_multiple_things" that has 6 assert statements
    When the test file is reviewed
    Then the review contains a warning about too many assertions in "test_multiple_things"

  Scenario: Quality check passes when score meets threshold
    Given a review result with overall score 0.75
    When the quality threshold is checked at 0.7
    Then the quality check returns true

  Scenario: Quality check fails when score is below threshold
    Given a review result with overall score 0.65
    When the quality threshold is checked at 0.7
    Then the quality check returns false

  Scenario: Formatted report includes score and test count
    Given a review result with score 0.85 and 3 tests
    When the report is formatted
    Then the report includes the score as a percentage
    And the report includes the test count
