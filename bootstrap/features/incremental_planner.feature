Feature: Incremental Planner
  As a TDD automation system
  I want to determine the next test increment to write
  So that I can progressively build functionality through test-driven development

  Scenario: Planning first test increment when no tests exist
    Given an IncrementalPlanner with empty test and source directories
    And an LLM client that returns "test_create_widget | Widget() creates instance without error | tests/test_widget.py | src/widget.py"
    When I call next_increment with requirement "Build a Widget class" and cycle_number 1
    Then I receive a TestIncrement with test_name "test_create_widget"
    And the TestIncrement has description "Widget() creates instance without error"
    And the TestIncrement has test_file ending with "test_widget.py"
    And the TestIncrement has implementation_file ending with "widget.py"

  Scenario: Planning returns COMPLETE when requirement is satisfied
    Given an IncrementalPlanner with existing tests and implementation
    And an LLM client that returns "COMPLETE"
    When I call next_increment with requirement "Build a calculator" and cycle_number 5
    Then I receive the COMPLETE sentinel object

  Scenario: Planning returns None when LLM response cannot be parsed
    Given an IncrementalPlanner with empty directories
    And an LLM client that returns "This is just some text without pipe delimiters"
    When I call next_increment with requirement "Build something" and cycle_number 1
    Then I receive None

  Scenario: Planning returns None when pipe-delimited line has wrong number of fields
    Given an IncrementalPlanner with empty directories
    And an LLM client that returns "test_name | description | only_three_fields"
    When I call next_increment with requirement "Build something" and cycle_number 1
    Then I receive None

  Scenario: Recording a test written during RED phase
    Given an IncrementalPlanner with empty directories
    When I call record_test_written with test_file "tests/test_calc.py", test_name "test_add", test_code "def test_add():\n    assert add(2, 3) == 5", and cycle_number 1
    Then the planner tracks this test internally for future planning context

  Scenario: Planning test for specific Gherkin scenario
    Given an IncrementalPlanner with empty directories
    And an LLM client that returns "test_bill_calculation | calculate_bill(40, 5.0, 0.15, 100) returns 11.0 | tests/test_billing.py | src/billing.py"
    And a scenario with name "Calculate basic bill" and steps ["Given consumption is 40 kWh", "When I calculate the bill", "Then the total is 11.0"]
    When I call next_increment_for_scenario with requirement "Electricity billing", cycle_number 2, the scenario, and gherkin_context "Feature: Billing"
    Then I receive a TestIncrement with test_name "test_bill_calculation"
    And the TestIncrement has description "calculate_bill(40, 5.0, 0.15, 100) returns 11.0"

  Scenario: Planning scenario test with explicit file paths
    Given an IncrementalPlanner with empty directories
    And an LLM client that returns "test_scenario | description with values | tests/test_feature.py | src/feature.py"
    And a scenario with name "Test scenario" and steps ["Given a precondition"]
    When I call next_increment_for_scenario with test_file "tests/custom_test.py" and impl_file "src/custom_impl.py"
    Then I receive a TestIncrement with test_file "tests/custom_test.py"
    And the TestIncrement has implementation_file "src/custom_impl.py"

  Scenario: Planning scenario test returns None on parse failure
    Given an IncrementalPlanner with empty directories
    And an LLM client that returns "unparseable response"
    And a scenario with name "Some scenario" and steps ["Given something"]
    When I call next_increment_for_scenario with requirement "Build feature", cycle_number 1, the scenario, and gherkin_context "Feature: Test"
    Then I receive None