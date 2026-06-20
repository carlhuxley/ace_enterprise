Feature: WorkerAgent code generation
  As a TDD orchestrator
  I want to generate test, implementation, and refactor code via an LLM
  So that I can drive the red-green-refactor cycle

  Scenario: Generate a new test without existing code
    Given a WorkerAgent with an LLM client
    And a PodSpec with feature requirement "calculate sum of two numbers"
    And the PodSpec test file name is "test_calculator.py"
    And no existing test code
    When I call generate_test with the spec
    Then the LLM receives a prompt containing "Add ONE new failing pytest test for: calculate sum of two numbers"
    And the LLM receives a prompt containing "Test file: test_calculator.py"
    And the returned code is extracted from the LLM response content

  Scenario: Generate a test with Gherkin context
    Given a WorkerAgent with an LLM client
    And a PodSpec with feature requirement "validate email format"
    And the PodSpec has gherkin_context "Scenario: Valid email\n  Given an email 'user@example.com'\n  Then it should be valid"
    When I call generate_test with the spec
    Then the LLM receives a prompt containing "Acceptance criteria (Gherkin — use exact values from relevant scenarios):"
    And the LLM receives a prompt containing "user@example.com"

  Scenario: Generate a test with existing code to preserve
    Given a WorkerAgent with an LLM client
    And a PodSpec with feature requirement "add subtraction"
    And existing test code "def test_add():\n    assert add(1, 2) == 3"
    When I call generate_test with the spec and existing code
    Then the LLM receives a prompt containing "Existing tests (KEEP ALL of these unchanged):"
    And the LLM receives a prompt containing "def test_add():"
    And the LLM receives a prompt containing "Output the COMPLETE test file"

  Scenario: Generate implementation with error output
    Given a WorkerAgent with an LLM client
    And a PodSpec with implementation file name "calculator.py"
    And error output "AssertionError: assert None == 3"
    When I call generate_implementation with the spec and error output
    Then the LLM receives a prompt containing "Write minimal implementation to make the failing tests pass"
    And the LLM receives a prompt containing "Implementation file: calculator.py"
    And the LLM receives a prompt containing "Test failure output:\nAssertionError: assert None == 3"

  Scenario: Generate implementation with playbook bullets
    Given a WorkerAgent with an LLM client and a playbook manager
    And the playbook manager returns bullets ["Use type hints", "Keep functions pure"] for section "strategies_and_hard_rules"
    And a PodSpec with implementation file name "utils.py"
    When I call generate_implementation with the spec
    Then the LLM receives a prompt containing "Playbook guidance:"
    And the LLM receives a prompt containing "- Use type hints"
    And the LLM receives a prompt containing "- Keep functions pure"

  Scenario: Generate implementation with context map and failing test IDs
    Given a WorkerAgent with an LLM client and a context map
    And the context map returns formatted nodes "def foo(x: int) -> int\nclass Bar" for test IDs ["test_foo", "test_bar"]
    And a PodSpec with implementation file name "module.py"
    And failing test IDs ["test_foo", "test_bar"]
    When I call generate_implementation with the spec and failing test IDs
    Then the LLM receives a prompt containing "Module context (AST signatures):"
    And the LLM receives a prompt containing "def foo(x: int) -> int"

  Scenario: Generate refactor with current code
    Given a WorkerAgent with an LLM client
    And a PodSpec with feature requirement "optimize sorting" and implementation file name "sorter.py"
    And current implementation code "def sort(items):\n    return sorted(items)"
    When I call generate_refactor with the spec and current code
    Then the LLM receives a prompt containing "Refactor the implementation while keeping tests green"
    And the LLM receives a prompt containing "Feature: optimize sorting"
    And the LLM receives a prompt containing "def sort(items):"

  Scenario: Extract code from fenced Python block
    Given a WorkerAgent with an LLM client
    And the LLM returns content "```python\ndef add(a, b):\n    return a + b\n```"
    And a PodSpec with feature requirement "addition"
    When I call generate_test with the spec
    Then the returned code is "def add(a, b):\n    return a + b"

  Scenario: Extract code from generic fenced block
    Given a WorkerAgent with an LLM client
    And the LLM returns content "```\ndef multiply(a, b):\n    return a * b\n```"
    And a PodSpec with feature requirement "multiplication"
    When I call generate_test with the spec
    Then the returned code is "def multiply(a, b):\n    return a * b"

  Scenario: Extract code from unclosed fence
    Given a WorkerAgent with an LLM client
    And the LLM returns content "```python\ndef divide(a, b):\n    return a / b"
    And a PodSpec with feature requirement "division"
    When I call generate_test with the spec
    Then the returned code is "def divide(a, b):\n    return a / b"

  Scenario: Return raw content when no code fence present
    Given a WorkerAgent with an LLM client
    And the LLM returns content "def subtract(a, b):\n    return a - b"
    And a PodSpec with feature requirement "subtraction"
    When I call generate_test with the spec
    Then the returned code is "def subtract(a, b):\n    return a - b"

  Scenario: Use custom temperature for LLM generation
    Given a WorkerAgent with an LLM client and temperature 0.7
    And a PodSpec with feature requirement "random choice"
    When I call generate_test with the spec
    Then the LLM is called with temperature 0.7