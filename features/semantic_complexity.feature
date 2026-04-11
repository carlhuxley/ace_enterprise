Feature: Semantic Code Complexity Analysis
  As a system administrator
  I want to analyze code complexity using AST-based metrics
  So that I can identify overly complex functions that need refactoring

  # Implementation: src/broker/semantic_analyzer.py
  # Tests: tests/test_semantic_analyzer.py

  Background:
    Given the SemanticCodeAnalyzer is initialized

  Scenario: Calculate cyclomatic complexity for a function
    Given the following Python code:
      """
      def process_order(order, user, discount=None):
          if not order:
              return None
          if not user.is_active:
              return {"error": "inactive_user"}
          if order.total > 1000:
              if discount:
                  order.total *= (1 - discount)
              else:
                  order.total *= 0.95
          elif order.total > 500:
              order.total *= 0.98
          return order
      """
    When I analyze the code for cyclomatic complexity
    Then function "process_order" should have complexity score 6
    And the complexity should be flagged as "moderate"

  Scenario: Apply complexity penalty for high-complexity functions
    Given a code submission with functions:
      | function_name    | complexity |
      | simple_getter    | 1          |
      | validate_input   | 8          |
      | complex_handler  | 15         |
    When I calculate the semantic quality score
    Then "complex_handler" should receive a penalty of -5 points
    And "simple_getter" should receive no penalty
    And "validate_input" should receive no penalty

  Scenario: Detect function length and nesting depth issues
    Given the following Python code:
      """
      def overly_long_function():
          x = 1
          y = 2
          z = 3
          if x:
              if y:
                  if z:
                      if x > y:
                          if y > z:
                              return "deeply nested"
          return x + y + z
      """
    When I analyze the code for maintainability
    Then the maximum nesting depth should be 5
    And the function should be flagged for "excessive_nesting"
