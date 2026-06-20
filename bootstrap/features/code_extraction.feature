Feature: Extract Python code from LLM responses

  Scenario: Extract code from python-tagged markdown fence
    Given a response containing "```python\nprint('hello')\n```"
    When extractCode is called
    Then the result is "print('hello')"

  Scenario: Extract code from untagged markdown fence
    Given a response containing "```\ndef foo():\n    pass\n```"
    When extractCode is called
    Then the result is "def foo():\n    pass"

  Scenario: Return trimmed response when no markdown fences present
    Given a response containing "  import sys  "
    When extractCode is called
    Then the result is "import sys"

  Scenario: Prefer python-tagged fence over untagged fence
    Given a response containing "```python\nx = 1\n```\nSome text\n```\ny = 2\n```"
    When extractCode is called
    Then the result is "x = 1"

  Scenario: Extract from untagged fence when python tag not present
    Given a response containing "Here is code:\n```\nresult = 42\n```\nDone"
    When extractCode is called
    Then the result is "result = 42"

  Scenario: Handle incomplete python-tagged fence by falling back
    Given a response containing "```python\nbroken code"
    When extractCode is called
    Then the result is "```python\nbroken code"

  Scenario: Handle incomplete untagged fence by falling back
    Given a response containing "```\nno closing fence"
    When extractCode is called
    Then the result is "```\nno closing fence"

  Scenario: Strip whitespace from plain response
    Given a response containing "\n\n  plain_code = True  \n\n"
    When extractCode is called
    Then the result is "plain_code = True"