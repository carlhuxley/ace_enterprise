Feature: Worker Agent Code Generation

  Scenario: Generating a new test in the RED phase
    Given a PodSpec with the following details:
      | feature_requirement | Calculate Fibonacci sequence |
      | test_file           | test_fib.py                  |
      | gherkin_context     | Scenario: Fib of 5 is 5      |
    And an LLM client that returns the following response:
      """
      def test_fibonacci_five():
          assert fibonacci(5) == 5