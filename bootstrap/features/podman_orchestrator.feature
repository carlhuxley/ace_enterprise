Feature: Podman Orchestrator
  The orchestrator executes code in an isolated container and returns test results.

  Scenario: Execute a single Python file as a string
    Given a container runner that returns exit code 0 with stdout "test passed"
    And the orchestrator is initialized with that runner
    When pulse is called with a single Python string "print('hello')"
    Then a PhaseResult is returned with passed=True
    And the output contains "test passed"

  Scenario: Execute multiple files as a dictionary
    Given a container runner that returns exit code 0 with stdout "multi-file test passed"
    And the orchestrator is initialized with that runner
    When pulse is called with files {"main.py": "import lib", "lib.py": "x = 1"}
    Then a PhaseResult is returned with passed=True
    And the output contains "multi-file test passed"

  Scenario: Test failure returns failed PhaseResult
    Given a container runner that returns exit code 1 with stderr "AssertionError: test failed"
    And the orchestrator is initialized with that runner
    When pulse is called with a single Python string "assert False"
    Then a PhaseResult is returned with passed=False
    And the error contains "AssertionError: test failed"

  Scenario: High severity Bandit findings block execution
    Given a container runner that returns exit code 0 with bandit_high=2, bandit_medium=1, bandit_low=3
    And the bandit_output is "B501: Insecure SSL usage"
    And the orchestrator is initialized with that runner
    When pulse is called with a single Python string "import ssl"
    Then a PhaseResult is returned with passed=False
    And the error contains "Bandit gate: HIGH=2 MEDIUM=1 LOW=3"
    And the error contains "B501: Insecure SSL usage"

  Scenario: Hash mismatch raises SecurityBreachError
    Given a container runner that returns h_executed="abc123" for proposed hash "def456"
    And the orchestrator is initialized with that runner
    When pulse is called with a single Python string "print('test')"
    Then a SecurityBreachError is raised
    And the error message contains "Hash mismatch: H_proposed=def456 H_executed=abc123"

  Scenario: Auto-start runner on first pulse when not started
    Given a container runner that is not started
    And the orchestrator is initialized with started=False
    When pulse is called with a single Python string "print('auto-start')"
    Then the runner is started automatically
    And a PhaseResult is returned

  Scenario: Restart runner on exception during pulse
    Given a container runner that raises an exception on first send_pulse
    And succeeds with exit code 0 on second send_pulse
    And the orchestrator is initialized with that runner
    When pulse is called with a single Python string "print('retry')"
    Then the runner is restarted
    And a PhaseResult is returned with passed=True

  Scenario: Stop the orchestrator
    Given a container runner that is started
    And the orchestrator is initialized with that runner
    When stop is called
    Then the runner is stopped