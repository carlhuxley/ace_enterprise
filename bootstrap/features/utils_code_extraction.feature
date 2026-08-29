Feature: Extract Python code from LLM responses

  Scenario: Extract code from a python-tagged fenced block
    Given a response:
      """
      Here is the function you asked for:
      def add(a, b):
          return a + b
      Let me know if you need anything else.
      """
    When extract_code is called with the response
    Then the result is:
      """
      def add(a, b):
          return a + b
      """

  Scenario: Extract code from a bare fenced block with no language tag
    Given a response:
      """
      print("hello world")
      """
    When extract_code is called with the response
    Then the result is:
      """
      print("hello world")
      """

  Scenario: Prefer the python-tagged block when both python and bare blocks are present
    Given a response:
      """
      def foo():
          pass
      Some explanatory text.
      other_code_here()
      """
    When extract_code is called with the response
    Then the result is:
      """
      def foo():
          pass
      """

  Scenario: Fall back to the full response when no code fences are present
    Given a response "  just a plain text response with no fences  "
    When extract_code is called with the response
    Then the result is "just a plain text response with no fences"

  Scenario: Fall back to the full stripped response when a python-tagged block has no closing fence
    Given a response:
      """
      def add(a, b):
          return a + b
      """
    When extract_code is called with the response
    Then the result equals the entire response with leading and trailing whitespace stripped

  Scenario: Fall back to the full stripped response when a bare block has no closing fence
    Given a response:
      """
      print("unclosed")
      """
    When extract_code is called with the response
    Then the result equals the entire response with leading and trailing whitespace stripped

  Scenario: Extracted code has surrounding whitespace stripped
    Given a response:
      """

          def add(a, b):
              return a + b

      """
    When extract_code is called with the response
    Then the result is:
      """
      def add(a, b):
              return a + b
      """