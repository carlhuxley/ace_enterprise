Feature: PodmanOrchestrator sandboxed code execution

  Background:
    Given a PodmanOrchestrator backed by a container runner test double

  Scenario: Submitting a single code string as a convenience shorthand
    When the orchestrator receives the pulse "def test_ok():\n    assert True"
    And the container runner executes it successfully with exit code 0
    Then the returned PhaseResult has passed equal to True

  Scenario: Successful multi-file workspace execution
    When the orchestrator receives a pulse containing files:
      | filename       | content                          |
      | main.go        | package main\nfunc main() {}     |
      | main_test.go   | package main\nfunc TestX(t){}    |
    And the container runner executes it successfully with exit code 0 and stdout "PASS"
    Then the returned PhaseResult has passed equal to True
    And the returned PhaseResult output is "PASS"

  Scenario: Failing test execution surfaces stderr as the error
    When the orchestrator receives the pulse "def test_fail():\n    assert False"
    And the container runner executes it with exit code 1 and stderr "AssertionError"
    Then the returned PhaseResult has passed equal to False
    And the returned PhaseResult error is "AssertionError"

  Scenario: High-severity security findings fail the pulse regardless of test outcome
    When the orchestrator receives the pulse "import os\nos.system('rm -rf /')"
    And the container runner executes it with exit code 0 and reports 2 high, 1 medium, 0 low security findings with output "B605: subprocess call"
    Then the returned PhaseResult has passed equal to False
    And the returned PhaseResult error contains "HIGH=2 MEDIUM=1 LOW=0"
    And the returned PhaseResult error contains "B605: subprocess call"

  Scenario: Executed hash mismatch is treated as a security breach
    When the orchestrator receives the pulse "print('hello')"
    And the container runner reports it executed code with a different content hash than what was submitted
    Then the orchestrator raises a SecurityBreachError

  Scenario: Orchestrator auto-starts the runner before the first pulse
    Given the orchestrator has not been started yet
    When the orchestrator receives the pulse "def test_ok():\n    assert True"
    Then the container runner is started before the pulse is executed

  Scenario: Runner failure during a pulse triggers an automatic restart and retry
    When the orchestrator receives the pulse "def test_ok():\n    assert True"
    And the container runner raises an error on the first send attempt but succeeds on the second attempt with exit code 0
    Then the container runner is restarted between the two attempts
    And the returned PhaseResult has passed equal to True

  Scenario: Successful execution passes through toolchain-formatted files
    When the orchestrator receives a pulse containing the file "main.go" with unformatted content
    And the container runner executes it successfully with exit code 0 and returns reformatted content for "main.go"
    Then the returned PhaseResult includes the reformatted content for "main.go"

  Scenario: Identical files produce the same canonical hash regardless of key order
    Given two file mappings with the same filenames and contents but inserted in different order
    When canonical_hash is computed for each mapping
    Then both hashes are identical