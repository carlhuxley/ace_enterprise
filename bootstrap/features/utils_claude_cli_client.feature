Feature: ClaudeCliClient text generation via local claude CLI

  As a caller needing LLM-generated text
  I want to invoke ClaudeCliClient.generate()
  So that I receive completion text and metadata without using an HTTP API

  Background:
    Given a ClaudeCliClient constructed with default timeout

  Scenario: Successful generation returns content and metadata
    Given the local claude CLI, when invoked, exits 0 and prints "def add(a, b):\n    return a + b" to stdout
    When generate() is called with prompt "Write a Python add function"
    Then the returned dict has "content" equal to "def add(a, b):\n    return a + b"
    And the returned dict has "prompt_tokens" equal to 0
    And the returned dict has "completion_tokens" equal to 0
    And the returned dict has "tokens_used" equal to 0
    And the returned dict has "actual_model" equal to "claude-cli"
    And the returned dict has "requested_model" equal to "claude-cli"
    And the returned dict has "provider" equal to "claude-cli"

  Scenario: Client exposes a stable model identity label
    When the client is inspected
    Then its "model" attribute is "claude-cli"

  Scenario: Transient CLI failure succeeds after retrying
    Given the local claude CLI exits 1 with stderr "temporary overload" on the first call
    And the local claude CLI exits 0 and prints "generated text" on the second call
    When generate() is called with prompt "Write a test"
    Then the returned dict has "content" equal to "generated text"

  Scenario: Missing claude binary is retried like a CLI failure
    Given invoking the claude CLI raises FileNotFoundError on the first call
    And the local claude CLI exits 0 and prints "recovered output" on the second call
    When generate() is called with prompt "Write a test"
    Then the returned dict has "content" equal to "recovered output"

  Scenario: Persistent CLI failure raises an error after exhausting retries
    Given the local claude CLI exits 1 with stderr "fatal error" on every call
    When generate() is called with prompt "Write a test"
    Then a RuntimeError is raised mentioning "claude CLI failed after 3 attempts"

  Scenario: A hung CLI call times out without being retried
    Given the local claude CLI call exceeds the configured timeout on the first call
    When generate() is called with prompt "Write a test"
    Then a timeout error is raised immediately
    And the claude CLI is not invoked a second time

  Scenario: max_tokens parameter is accepted but does not affect the call
    Given the local claude CLI, when invoked, exits 0 and prints "short reply" to stdout
    When generate() is called with prompt "Write a haiku" and max_tokens 5
    Then the returned dict has "content" equal to "short reply"