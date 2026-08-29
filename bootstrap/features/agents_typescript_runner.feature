Feature: TypeScript pulse runner (test execution + security scan)

  As a caller of TypeScriptRunner, I send a set of TypeScript files and
  receive back a PulseResult describing whether the tests passed and
  whether static security scanning found any issues.

  Scenario: All tests pass and no security issues are found
    Given a running TypeScriptRunner
    And a pulse containing "sum.ts" and "sum.test.ts" whose tests all pass
    And "sum.ts" contains no insecure patterns
    When send_pulse is called with these files
    Then the result exit_code is 0
    And the result bandit_clean is true
    And the result bandit_high is 0

  Scenario: Some tests fail
    Given a running TypeScriptRunner
    And a pulse containing "add.ts" and "add.test.ts" where one assertion fails
    When send_pulse is called with these files
    Then the result exit_code is 1
    And the result stdout contains "FAIL"
    And the result stdout contains the failing assertion's title

  Scenario: Static scan finds high and medium severity issues
    Given a running TypeScriptRunner
    And a pulse containing "risky.ts" which triggers eslint-plugin-security errors and warnings
    When send_pulse is called with these files
    Then the result bandit_high is greater than 0
    And the result bandit_medium is greater than or equal to 0
    And the result bandit_clean is false

  Scenario: Pulse with no TypeScript files skips the security scan
    Given a running TypeScriptRunner
    And a pulse containing only "notes.txt" with no ".ts" files
    When send_pulse is called with these files
    Then the result bandit_high is 0
    And the result bandit_medium is 0
    And the result bandit_clean is true

  Scenario: Test run times out and the container is restarted
    Given a running TypeScriptRunner
    And a pulse whose tests hang beyond the configured test timeout
    When send_pulse is called with these files
    Then the result exit_code is 1
    And the result stdout is empty
    And the result stderr contains "vitest timed out"
    And a subsequent send_pulse call on the same runner succeeds normally

  Scenario: Test results cannot be parsed as JSON
    Given a running TypeScriptRunner
    And a pulse where the test process produces no valid results output
    When send_pulse is called with these files
    Then the result exit_code is 1

  Scenario: Building the TypeScript harness image
    Given a Containerfile at "docker/harness/Containerfile.ts" and build context "docker/harness"
    When build_ts_image is called with default arguments
    Then a container image tagged "localhost/ace-ts-harness:latest" is available
    And calling build_ts_image again with the same arguments succeeds without error

  Scenario: Each pulse produces a hash of the executed workspace files
    Given a running TypeScriptRunner
    And a pulse containing "util.ts" and "util.test.ts"
    When send_pulse is called with these files
    Then the result h_executed is a non-empty hash value