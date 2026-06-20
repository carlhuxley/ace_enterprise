Feature: Claude CLI Client

  Scenario: Generate text from a prompt with default temperature
    Given a ClaudeCliClient instance with default timeout
    When generate is called with prompt "Write hello world"
    Then a dictionary is returned with key "content" containing the response text
    And the dictionary contains key "prompt_tokens" with value 0
    And the dictionary contains key "completion_tokens" with value 0
    And the dictionary contains key "tokens_used" with value 0

  Scenario: Generate text with explicit temperature parameter
    Given a ClaudeCliClient instance with default timeout
    When generate is called with prompt "Explain Python" and temperature 0.7
    Then a dictionary is returned with key "content" containing the response text
    And the dictionary contains key "prompt_tokens" with value 0
    And the dictionary contains key "completion_tokens" with value 0
    And the dictionary contains key "tokens_used" with value 0

  Scenario: Initialize client with custom timeout
    Given a ClaudeCliClient instance with timeout 600
    When generate is called with prompt "Analyze this code"
    Then a dictionary is returned with key "content" containing the response text
    And the dictionary contains key "prompt_tokens" with value 0
    And the dictionary contains key "completion_tokens" with value 0
    And the dictionary contains key "tokens_used" with value 0

  Scenario: CLI subprocess returns non-zero exit code
    Given a ClaudeCliClient instance with default timeout
    When generate is called with a prompt that causes the claude CLI to exit with code 1
    Then a RuntimeError is raised
    And the error message contains "claude CLI error (exit 1)"

  Scenario: CLI subprocess times out
    Given a ClaudeCliClient instance with timeout 1
    When generate is called with a prompt that takes longer than 1 second to process
    Then a subprocess.TimeoutExpired exception is raised

  Scenario: Response content is stripped of whitespace
    Given a ClaudeCliClient instance with default timeout
    When generate is called with prompt "Test prompt"
    And the claude CLI returns output with leading and trailing whitespace
    Then the returned dictionary "content" value has whitespace removed