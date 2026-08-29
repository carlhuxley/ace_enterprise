Feature: Test Review Agent
  As a developer preparing for TDD, I want automated feedback on the quality
  of my test files so that I can fix issues before ACE learns from them.

  Scenario: Reviewing a file with no test functions
    Given a test file "empty_tests.py" containing no functions starting with "test_"
    When the file is reviewed by the Test Review Agent
    Then the result reports a test count of 0
    And the result contains a critical issue about no test functions being found
    And the overall score is 0.0

  Scenario: Reviewing a test function with no assertions
    Given a test file "no_assert.py" containing:
      """
      def test_creates_user():
          user = create_user("alice")
      """
    When the file is reviewed by the Test Review Agent
    Then the result reports a test count of 1
    And the result contains a critical issue that test "test_creates_user" has no assertions
    And the issue includes a suggestion to add assert statements

  Scenario: Reviewing a test with a vague name
    Given a test file "vague_name.py" containing:
      """
      def test_basic():
          result = add(2, 2)
          assert result == 4
      """
    When the file is reviewed by the Test Review Agent
    Then the result contains a warning that test name "test_basic" is too vague
    And the issue includes a suggestion to use a more descriptive name

  Scenario: Reviewing a test with a descriptive name
    Given a test file "descriptive_name.py" containing:
      """
      def test_add_returns_sum_when_given_two_positive_numbers():
          result = add(2, 2)
          assert result == 4
      """
    When the file is reviewed by the Test Review Agent
    Then the result lists a strength noting test "test_add_returns_sum_when_given_two_positive_numbers" has a descriptive name

  Scenario: Reviewing a test with too many assertions
    Given a test file "many_asserts.py" containing a test function "test_user_creation" with 6 assert statements
    When the file is reviewed by the Test Review Agent
    Then the result contains a warning that test "test_user_creation" has 6 assertions
    And the issue includes a suggestion to split the test into separate tests

  Scenario: Determining good quality against a custom threshold
    Given a reviewed test file with an overall score of 0.65
    When checking if the result is good quality with threshold 0.6
    Then the check returns true
    When checking if the result is good quality with threshold 0.7
    Then the check returns false

  Scenario: Detecting critical issues in a review result
    Given a reviewed test file whose issues include one with severity "critical"
    When checking if the result has critical issues
    Then the check returns true

  Scenario: Formatting a human-readable report
    Given a reviewed test file "sample_tests.py" with an overall score of 0.9 and 3 tests found
    When the result is formatted as a report
    Then the report includes the text "TEST REVIEW: sample_tests.py"
    And the report includes the text "Overall Score: 90.0%"
    And the report includes the text "Tests Found: 3"
    And the report includes the text "Test quality is GOOD - safe to proceed with TDD"