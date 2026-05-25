Feature: Worker agent TDD code generation

  WorkerAgent produces raw Python code strings for the RED, GREEN, and REFACTOR
  phases of a TDD cycle by building a prompt and delegating to an LLM client,
  then extracting and returning the code from the response.

  Scenario: generate_test returns code stripped from a python-fenced LLM response
    Given a WorkerAgent backed by an LLM client
    And a PodSpec with feature requirement "add two integers" and test file "test_calc.py"
    And the LLM client returns a response whose content is:
      """
      def test_add():
          assert add(1, 2) == 3
      """
    When generate_test is called with the PodSpec
    Then the returned string is:
      """
      def test_add():
          assert add(1, 2) == 3
      """

  Scenario: generate_test returns code from a generic-fenced LLM response
    Given a WorkerAgent backed by an LLM client
    And a PodSpec with feature requirement "add two integers" and test file "test_calc.py"
    And the LLM client returns a response whose content is:
      """
      def test_add():
          assert add(1, 2) == 3
      """
    When generate_test is called with the PodSpec
    Then the returned string is:
      """
      def test_add():
          assert add(1, 2) == 3
      """

  Scenario: generate_test returns raw content when the LLM response contains no code fences
    Given a WorkerAgent backed by an LLM client
    And a PodSpec with feature requirement "add two integers" and test file "test_calc.py"
    And the LLM client returns a response whose content is "def test_add():\n    assert add(1, 2) == 3"
    When generate_test is called with the PodSpec
    Then the returned string is "def test_add():\n    assert add(1, 2) == 3"

  Scenario: generate_test recovers code from a truncated response with an unclosed fence
    Given a WorkerAgent backed by an LLM client
    And a PodSpec with feature requirement "add two integers" and test file "test_calc.py"
    And the LLM client returns a response whose content is:
      """
      def test_add():
          assert add(1, 2) == 3
      """
    When generate_test is called with the PodSpec
    Then the returned string is:
      """
      def test_add():
          assert add(1, 2) == 3
      """

  Scenario: generate_implementation passes the configured temperature to the LLM client
    Given a WorkerAgent with temperature 0.7 backed by a recording LLM client
    And the LLM client returns a response whose content is "```python\npass\n```"
    And a PodSpec with feature requirement "sort a list" and implementation file "sort.py"
    When generate_implementation is called with the PodSpec
    Then the LLM client received exactly one generate call with temperature 0.7

  Scenario: generate_implementation resolves module context from the context map when none is supplied
    Given a WorkerAgent backed by an LLM client and a context map
    And the context map returns "def bubble_sort(lst: list) -> list: ..." for test IDs ["test_sort.py::test_bubble"]
    And the LLM client returns a response whose content is "```python\ndef bubble_sort(lst): return sorted(lst)\n```"
    And a PodSpec with feature requirement "sort a list" and implementation file "sort.py"
    When generate_implementation is called with failing test IDs ["test_sort.py::test_bubble"] and no explicit module context
    Then the returned string is "def bubble_sort(lst): return sorted(lst)"

  Scenario: generate_implementation uses explicit module context and does not query the context map
    Given a WorkerAgent backed by an LLM client and a context map
    And the LLM client returns a response whose content is "```python\ndef add(a, b): return a + b\n```"
    And a PodSpec with feature requirement "add two integers" and implementation file "calc.py"
    When generate_implementation is called with module context "def merge_sort(lst): ..." and failing test IDs ["test_calc.py::test_add"]
    Then the context map is not queried
    And the returned string is "def add(a, b): return a + b"

  Scenario: generate_refactor returns refactored code extracted from the LLM response
    Given a WorkerAgent backed by an LLM client
    And a PodSpec with feature requirement "add two integers" and implementation file "calc.py"
    And the LLM client returns a response whose content is "```python\ndef add(a, b): return a + b\n```"
    When generate_refactor is called with the PodSpec and current code:
      """
      def add(a, b):
          result = a + b
          return result
      """
    Then the returned string is "def add(a, b): return a + b"