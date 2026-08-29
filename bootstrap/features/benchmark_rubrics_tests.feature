Feature: TestWritingRubric evaluates test suite code quality

  Scenario: Rubric identifies itself as "test_writing"
    When the rubric's name is requested
    Then the returned name is "test_writing"

  Scenario: Rubric exposes four scoring dimensions whose weights sum to 1.0
    When the rubric's dimensions are requested
    Then the returned dimensions include "edge_cases" with weight 0.30
    And the returned dimensions include "assertions" with weight 0.30
    And the returned dimensions include "naming" with weight 0.20
    And the returned dimensions include "coverage" with weight 0.20
    And the sum of all dimension weights is 1.0

  Scenario: Edge case dimension rewards code exercising multiple boundary conditions
    Given the following test output:
      """
      def test_handles_none_and_empty(self):
          assert process(None) is None
          assert process([]) == []
          assert process("") == ""
          assert process(0) == 0
          assert process(-1) == -1
      """
    When the rubric scores the "edge_cases" dimension for this output
    Then the returned score is 100.0

  Scenario: Edge case dimension gives a low score when no boundary conditions are present
    Given the following test output:
      """
      def test_addition():
          assert add(2, 3) == 5
      """
    When the rubric scores the "edge_cases" dimension for this output
    Then the returned score is 0.0

  Scenario: Assertions dimension scales with assert density per test function
    Given the following test output:
      """
      def test_one():
          assert 1 == 1
          assert 2 == 2

      def test_two():
          assert 3 == 3
          assert 4 == 4
      """
    When the rubric scores the "assertions" dimension for this output
    Then the returned score is 100.0

  Scenario: Naming dimension favors descriptive multi-part test function names
    Given the following test output:
      """
      def test_returns_correct_sum_for_positive_numbers():
          assert add(2, 3) == 5

      def test_basic():
          assert add(0, 0) == 0
      """
    When the rubric scores the "naming" dimension for this output
    Then the returned score is 50.0

  Scenario Outline: Coverage dimension maps test function count to fixed score tiers
    Given test output containing <count> independent test functions
    When the rubric scores the "coverage" dimension for this output
    Then the returned score is <score>

    Examples:
      | count | score |
      | 1     | 40.0  |
      | 2     | 60.0  |
      | 4     | 80.0  |
      | 5     | 100.0 |

  Scenario: Unparseable code yields a zero score for syntax-dependent dimensions
    Given the following test output:
      """
      def test_broken(:
          assert True
      """
    When the rubric scores the "assertions" dimension for this output
    Then the returned score is 0.0
    When the rubric scores the "naming" dimension for this output
    Then the returned score is 0.0
    When the rubric scores the "coverage" dimension for this output
    Then the returned score is 0.0