Feature: Reverse-engineering Gherkin specifications from Python code and tests
  As a developer preparing to refactor or migrate a legacy module
  I want to extract Gherkin feature files and step definitions from existing source and test code
  So that I have a specification to validate behavior is preserved

  Scenario: Extracting from a documented class with a fully-tested, asserted scenario yields maximum confidence
    Given a source file "calculator.py" containing:
      """
      class Calculator:
          \"\"\"A simple calculator.\"\"\"
          def add(self, a, b):
              return a + b
      """
    And a test file "test_calculator.py" containing:
      """
      def test_add_two_numbers():
          calc = Calculator()
          calc.add(5, 3)
          assertEqual(calc.total, 8)
      """
    When I call extract_from_codebase with the source file and the test file
    Then the result's feature should be named "calculator"
    And the feature description should be "A simple calculator."
    And the feature should contain a scenario named "Add two numbers"
    And that scenario's steps should be "Given a calculator", "When I add with 5, 3", "Then calc.total should be 8"
    And the confidence score should be 1.0
    And there should be no warnings

  Scenario: A source file with no matching tests produces a warning and reduced confidence
    Given a source file "calculator.py" containing a class "Calculator" with a docstring and one method "add"
    And a test file "test_calculator.py" containing no functions prefixed with "test_"
    When I call extract_from_codebase with the source file and the test file
    Then the result's warnings should include "No tests found - extraction based solely on code structure"
    And the confidence score should be 0.2

  Scenario: A source file with no classes or functions produces a structural warning and zero confidence
    Given a source file "constants.py" containing only module-level variable assignments
    And a test file "test_constants.py" containing no functions prefixed with "test_"
    When I call extract_from_codebase with the source file and the test file
    Then the result's warnings should include "No classes or functions found in code"
    And the result's warnings should include "No tests found - extraction based solely on code structure"
    And the confidence score should be 0.0

  Scenario: Writing an extracted feature renders it deterministically as a .feature file and creates missing directories
    Given an ExtractionResult whose feature is named "calculator" with one scenario "Add two numbers" made of the steps "Given a calculator", "When I add with 5, 3", "Then calc.total should be 8"
    And the output path "output/calculator.feature" does not yet exist, nor does its parent directory
    When I call write_gherkin_file with that feature and output path
    Then the file "output/calculator.feature" should exist
    And its contents should be:
      """
      Feature: calculator

        Scenario: Add two numbers
          Given a calculator
          When I add with 5, 3
          Then calc.total should be 8

      """

  Scenario: Writing a feature with pre-rendered Gherkin text writes that text verbatim instead of the deterministic rendering
    Given the same extracted feature as above
    And a pre-rendered Gherkin string "Feature: Calculator\n\n  Scenario: Add two numbers\n    Given a calculator\n    When I add with a quantity of 5 and 3\n    Then the total should be 8\n"
    When I call write_gherkin_file passing that pre-rendered string as the gherkin_text argument
    Then the file at the output path should contain exactly the pre-rendered string, unchanged

  Scenario: Writing step definitions produces a Python file importing behave and the analyzed classes, with one decorated function per step
    Given step definitions for the steps "a calculator", "I add with 5, 3", and "calc.total should be 8"
    And code analysis for "calculator.py" containing the class "Calculator"
    When I call write_step_definitions with those step definitions, the code analysis, and output path "output/steps.py"
    Then the file "output/steps.py" should start with "from behave import given, when, then"
    And it should contain "from calculator import Calculator"
    And it should contain a function decorated "@given('a calculator')"
    And it should contain a function decorated "@given('I add with 5, 3')"
    And it should contain a function decorated "@given('calc.total should be 8')"

  Scenario: Configuring the agent with an LLM client that returns valid Gherkin populates a refined feature file
    Given an agent constructed with an llm_client whose generate() call returns a response containing "Feature: Calculator\n\n  Scenario: Add two numbers\n    Given I have a calculator\n    When I add 5 and 3\n    Then the total is 8\n"
    When I call extract_from_codebase with the source file and the test file from the first scenario
    Then the result's refined_gherkin should equal the text returned by the llm_client
    And the result's feature and step_definitions should still reflect the deterministic extraction

  Scenario: Configuring the agent with an LLM client that returns malformed output falls back to no refined text
    Given an agent constructed with an llm_client whose generate() call returns a response with no "Feature:" header
    When I call extract_from_codebase with the source file and the test file from the first scenario
    Then the result's refined_gherkin should be None
    And the result's feature and step_definitions should still reflect the deterministic extraction