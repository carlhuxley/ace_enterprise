Feature: Context Map extraction and signature querying
  As a caller analyzing a Python codebase
  I want to build a context map of function/class signatures from source files
  And query which signatures are relevant to a set of test node IDs

  Scenario: Building a context map from a file with a top-level function
    Given a Python file "sample.py" containing:
      """
      def greet(name: str) -> str:
          return f"hello {name}"
      """
    When I build a context map from ["sample.py"]
    Then the context map contains 1 signature
    And the signature has qualified name "greet"
    And the signature has kind "function"
    And the signature has parameters ["name: str"]
    And the signature has return annotation "str"

  Scenario: Building a context map from a file with a class and methods
    Given a Python file "widget.py" containing:
      """
      class Widget:
          def render(self, size: int = 10) -> None:
              pass
      """
    When I build a context map from ["widget.py"]
    Then the context map contains 2 signatures
    And one signature has qualified name "Widget" with kind "class"
    And one signature has qualified name "Widget.render" with kind "method"
    And the "Widget.render" signature has parameters ["self", "size: int = 10"]

  Scenario: Building a context map skips files that do not exist
    Given the file "missing.py" does not exist on disk
    When I build a context map from ["missing.py"]
    Then the context map contains 0 signatures

  Scenario: Building a context map skips files with invalid syntax
    Given a Python file "broken.py" containing:
      """
      def broken(:
      """
    When I build a context map from ["broken.py"]
    Then the context map contains 0 signatures

  Scenario: Formatting a signature compactly
    Given a Python file "math_utils.py" containing:
      """
      def add(a: int, b: int) -> int:
          return a + b
      """
    When I build a context map from ["math_utils.py"]
    And I format the "add" signature compactly
    Then the formatted output is "add(a: int, b: int) -> int  # math_utils.py:1"

  Scenario: Querying nodes relevant to a test that references a function
    Given a Python file "app.py" containing:
      """
      def compute_total(items):
          return sum(items)
      """
    And a Python test file "test_app.py" containing:
      """
      def test_compute_total():
          compute_total([1, 2, 3])
      """
    And a context map built from ["app.py"]
    When I query nodes relevant to test IDs ["test_app.py::test_compute_total"]
    Then the result contains the signature named "compute_total"

  Scenario: Querying nodes relevant to tests with an empty test ID list
    Given a context map built from ["app.py"]
    When I query nodes relevant to test IDs []
    Then the result is an empty list

  Scenario: Querying nodes relevant to tests referencing a nonexistent test file
    Given a context map built from ["app.py"]
    When I query nodes relevant to test IDs ["nonexistent_test.py::test_something"]
    Then the result is an empty list