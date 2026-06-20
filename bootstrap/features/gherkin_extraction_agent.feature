Feature: Gherkin Extraction Agent
  As a developer
  I want to extract Gherkin scenarios from existing code and tests
  So that I can document behavior and enable safe refactoring

  Scenario: Analyze Python source code file
    Given a Python file at "calculator.py" containing a Calculator class with add and subtract methods
    When I analyze the code file
    Then the code analysis should contain 1 class
    And the class should be named "Calculator"
    And the class should have 2 methods
    And the method names should include "add" and "subtract"

  Scenario: Analyze test file with test functions
    Given a test file at "test_calculator.py" containing test_add_two_numbers and test_subtract_returns_difference
    When I analyze the test file
    Then the test analysis should contain 2 scenarios
    And the first scenario should be named "test_add_two_numbers"
    And each scenario should have a line number

  Scenario: Extract Gherkin from codebase with matching tests
    Given a code file at "calculator.py" with a Calculator class
    And a test file at "test_calculator.py" with 3 test functions
    When I extract Gherkin from the codebase
    Then the extraction result should contain a feature
    And the feature should have 3 scenarios
    And the extraction result should contain step definitions
    And the confidence score should be between 0.0 and 1.0

  Scenario: Generate feature with custom name
    Given a code file at "math_ops.py"
    And a test file at "test_math_ops.py"
    When I extract Gherkin with feature name "Mathematical Operations"
    Then the feature name should be "Mathematical Operations"

  Scenario: Calculate high confidence score with good test coverage
    Given a code file with 1 class containing 2 methods
    And a test file with 2 test scenarios
    And the class has a docstring
    And all test scenarios have assertions
    When I extract Gherkin from the codebase
    Then the confidence score should be greater than 0.8

  Scenario: Generate warnings for missing tests
    Given a code file at "service.py" with a Service class
    And a test file at "test_service.py" with no test functions
    When I extract Gherkin from the codebase
    Then the warnings list should contain "No tests found - extraction based solely on code structure"

  Scenario: Write Gherkin feature to file
    Given an extraction result with a feature named "User Authentication"
    And the feature has 2 scenarios
    When I write the Gherkin file to "features/authentication.feature"
    Then the file should exist at "features/authentication.feature"
    And the file should contain "Feature: User Authentication"
    And the file should contain "Scenario:" exactly 2 times

  Scenario: Write step definitions to Python file
    Given an extraction result with 5 step definitions
    And a code analysis with class "Calculator" from "calculator.py"
    When I write step definitions to "steps/calculator_steps.py"
    Then the file should exist at "steps/calculator_steps.py"
    And the file should contain "from behave import given, when, then"
    And the file should contain "from calculator import Calculator"
    And the file should contain "def step_impl(context):" exactly 5 times