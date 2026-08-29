Feature: IncrementalPlanner determines the next TDD test increment

  Background:
    Given an IncrementalPlanner configured with a test directory "tests/" and a source directory "src/"

  Scenario: Requirement is judged satisfied by the LLM
    Given the LLM client responds with "COMPLETE" when asked for the next increment
    When next_increment is called with requirement "Widget can add two numbers" and cycle_number 4
    Then the result is the COMPLETE sentinel

  Scenario: LLM proposes a well-formed next test
    Given the LLM client responds with "test_add_returns_sum | Widget.add(2, 3) returns 5 | tests/test_widget.py | src/widget.py"
    When next_increment is called with requirement "Widget can add two numbers" and cycle_number 2
    Then a TestIncrement is returned with test_name "test_add_returns_sum"
    And the TestIncrement description is "Widget.add(2, 3) returns 5"
    And the TestIncrement test_file is "tests/test_widget.py"
    And the TestIncrement implementation_file is "src/widget.py"

  Scenario: LLM response uses a nested path for the test file
    Given the LLM client responds with "test_can_be_created | Widget() creates instance without error | deep/nested/tests/test_widget.py | deep/nested/src/widget.py"
    When next_increment is called with requirement "Widget exists" and cycle_number 1
    Then a TestIncrement is returned with test_file "tests/test_widget.py"
    And the TestIncrement implementation_file is "src/widget.py"

  Scenario: LLM response contains no pipe-delimited line
    Given the LLM client responds with "I think the widget is basically done for now."
    When next_increment is called with requirement "Widget can add two numbers" and cycle_number 3
    Then the result is None

  Scenario: LLM response has too few pipe-delimited fields
    Given the LLM client responds with "test_add_returns_sum | Widget.add(2, 3) returns 5"
    When next_increment is called with requirement "Widget can add two numbers" and cycle_number 2
    Then the result is None

  Scenario: LLM response wraps fields in markdown emphasis characters
    Given the LLM client responds with "**test_add_returns_sum** | `Widget.add(2, 3) returns 5` | tests/test_widget.py | src/widget.py"
    When next_increment is called with requirement "Widget can add two numbers" and cycle_number 2
    Then a TestIncrement is returned with test_name "test_add_returns_sum"
    And the TestIncrement description is "Widget.add(2, 3) returns 5"

  Scenario: Planning a test for a specific Gherkin scenario with explicit file paths
    Given a Gherkin scenario named "Add two positive numbers" with steps describing Widget.add(2, 3) returning 5
    And the LLM client responds with "test_add_positive_numbers | Widget.add(2, 3) returns 5 | tests/test_widget.py | src/widget.py"
    When next_increment_for_scenario is called with requirement "Widget can add two numbers", cycle_number 2, test_file "tests/test_widget.py", and impl_file "src/widget.py"
    Then a TestIncrement is returned with test_file "tests/test_widget.py"
    And the TestIncrement implementation_file is "src/widget.py"
    And the TestIncrement test_name is "test_add_positive_numbers"

  Scenario: Planning a test for a specific Gherkin scenario fails to parse
    Given a Gherkin scenario named "Add two positive numbers" with steps describing Widget.add(2, 3) returning 5
    And the LLM client responds with "Sure, here's a test idea for you."
    When next_increment_for_scenario is called with requirement "Widget can add two numbers" and cycle_number 2
    Then the result is None