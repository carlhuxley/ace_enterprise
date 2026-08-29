Feature: WorkerAgent code generation

  Scenario: Generating a test extracts code from a fenced python response
    Given a PodSpec with feature_requirement "add two numbers" and test_file "test_math.py"
    And an LLM client that returns content "Here you go:\n```python\ndef test_add():\n    assert add(2, 3) == 5\n```"
    When generate_test is called with that spec
    Then the returned string is "def test_add():\n    assert add(2, 3) == 5"

  Scenario: Generating a test extracts code from a generic fenced block when no python fence is present
    Given a PodSpec with feature_requirement "add two numbers" and test_file "test_math.py"
    And an LLM client that returns content "```\ndef test_add():\n    assert add(2, 3) == 5\n```"
    When generate_test is called with that spec
    Then the returned string is "def test_add():\n    assert add(2, 3) == 5"

  Scenario: Generating implementation extracts code from an unclosed code fence
    Given a PodSpec with feature_requirement "add two numbers" and implementation_file "math.py"
    And an LLM client that returns content "```python\ndef add(a, b):\n    return a + b"
    When generate_implementation is called with that spec
    Then the returned string is "def add(a, b):\n    return a + b"

  Scenario: Generating implementation extracts code when the LLM omits code fences entirely
    Given a PodSpec with feature_requirement "add two numbers" and implementation_file "math.py"
    And an LLM client that returns content "Sure, here is the implementation:\ndef add(a, b):\n    return a + b"
    When generate_implementation is called with that spec
    Then the returned string is "def add(a, b):\n    return a + b"

  Scenario: Generating a test with existing test code instructs preservation of existing tests
    Given a PodSpec with feature_requirement "add two numbers" and test_file "test_math.py"
    And existing test code "def test_zero():\n    assert add(0, 0) == 0"
    And an LLM client that returns content "```python\ndef test_zero():\n    assert add(0, 0) == 0\n\n\ndef test_add():\n    assert add(2, 3) == 5\n```"
    When generate_test is called with that spec and the existing test code
    Then the returned string contains both "def test_zero" and "def test_add"

  Scenario: Generating implementation passes failing test output and module context to the LLM
    Given a PodSpec with feature_requirement "add two numbers" and implementation_file "math.py"
    And a prior test failure output "AssertionError: assert 4 == 5"
    And an LLM client that returns content "```python\ndef add(a, b):\n    return a + b\n```"
    When generate_implementation is called with that spec and the failure output
    Then the returned string is "def add(a, b):\n    return a + b"

  Scenario: Generating a refactor returns cleaned-up code for the existing implementation
    Given a PodSpec with feature_requirement "add two numbers" and implementation_file "math.py"
    And current implementation code "def add(a,b):\n  return a+b"
    And an LLM client that returns content "```python\ndef add(a: int, b: int) -> int:\n    return a + b\n```"
    When generate_refactor is called with that spec and the current code
    Then the returned string is "def add(a: int, b: int) -> int:\n    return a + b"

  Scenario: An LLM response with no code fence and no recognizable Python start is returned verbatim and trimmed
    Given a PodSpec with feature_requirement "add two numbers" and implementation_file "math.py"
    And an LLM client that returns content "  I could not generate a solution.  "
    When generate_implementation is called with that spec
    Then the returned string is "I could not generate a solution."