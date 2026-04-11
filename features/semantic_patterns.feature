Feature: Semantic Code Pattern Detection
  As a system administrator
  I want to detect design patterns and code quality indicators
  So that I can reward good practices like dependency injection and type hints

  # Implementation: src/broker/semantic_analyzer.py
  # Tests: tests/test_semantic_analyzer.py

  Background:
    Given the SemanticCodeAnalyzer is initialized

  Scenario: Reward dependency injection patterns
    Given the following Python code:
      """
      class OrderService:
          def __init__(self, repository, notifier, logger=None):
              self.repository = repository
              self.notifier = notifier
              self.logger = logger or default_logger

          def process(self, order_id):
              order = self.repository.get(order_id)
              self.notifier.send(order)
              return order
      """
    When I analyze the code for design patterns
    Then the analyzer should detect "dependency_injection" pattern
    And a maintainability bonus of +5 points should be applied

  Scenario: Reward type hints coverage
    Given the following Python code:
      """
      from typing import Optional, List

      def calculate_total(items: List[dict], discount: Optional[float] = None) -> float:
          total: float = sum(item['price'] for item in items)
          if discount:
              total *= (1 - discount)
          return total
      """
    When I analyze the code for type hint coverage
    Then the type hint coverage should be at least 80%
    And a maintainability bonus of +3 points should be applied

  Scenario: Detect code duplication patterns
    Given the following Python code with duplication:
      """
      def process_order_v1(order):
          if order.total > 100:
              order.discount = 0.1
          order.tax = order.total * 0.08
          order.final = order.total - order.discount + order.tax
          return order

      def process_order_v2(order):
          if order.total > 100:
              order.discount = 0.1
          order.tax = order.total * 0.08
          order.final = order.total - order.discount + order.tax
          return order
      """
    When I analyze the code for duplication
    Then the analyzer should detect "code_duplication" issue
    And the duplication percentage should be above 50%
    And a duplication penalty should be applied
