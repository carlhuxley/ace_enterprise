Feature: TypeScript Runner
  A test runner that executes TypeScript tests using vitest in a containerized environment

  Scenario: Build TypeScript harness image with default parameters
    Given no existing TypeScript harness image
    When build_ts_image is called with no arguments
    Then a container image is built with tag "localhost/ace-ts-harness:latest"
    And the build uses Containerfile at "docker/harness/Containerfile.ts"
    And the build context is "docker/harness"

  Scenario: Build TypeScript harness image with custom parameters
    Given no existing TypeScript harness image
    When build_ts_image is called with containerfile "custom/Containerfile", context "custom/dir", and tag "my-registry/ts:v1"
    Then a container image is built with tag "my-registry/ts:v1"
    And the build uses Containerfile at "custom/Containerfile"
    And the build context is "custom/dir"

  Scenario: Initialize TypeScript runner with default settings
    When a TypeScriptRunner is created with no arguments
    Then the runner is configured with image "localhost/ace-ts-harness:latest"
    And the runner has cpus set to "0.5"
    And the runner has memory set to "256m"
    And the runner has test_timeout set to 10

  Scenario: Initialize TypeScript runner with custom resource limits
    When a TypeScriptRunner is created with container_name "my-ts-test", cpus "2.0", memory "512m", and test_timeout 30
    Then the runner is configured with container_name "my-ts-test"
    And the runner has cpus set to "2.0"
    And the runner has memory set to "512m"
    And the runner has test_timeout set to 30

  Scenario: Send pulse with passing TypeScript tests
    Given a TypeScriptRunner instance with a running container
    And files containing "test_example.ts" with passing test code
    When send_pulse is called with the files dictionary
    Then a PulseResult is returned with exit_code 0
    And the result stdout contains test output
    And the result bandit_output is empty string
    And the result bandit_clean is True
    And the result h_executed is a hash of the executed files

  Scenario: Send pulse with failing TypeScript tests
    Given a TypeScriptRunner instance with a running container
    And files containing "test_failure.ts" with a failing assertion
    When send_pulse is called with the files dictionary
    Then a PulseResult is returned with exit_code 1
    And the result stdout contains "FAIL" and the failure message
    And the result stderr contains vitest error output
    And the result bandit_clean is True
    And the result h_executed is a hash of the executed files

  Scenario: Send pulse with multiple test files
    Given a TypeScriptRunner instance with a running container
    And files containing "test_one.ts" with passing tests
    And files containing "test_two.ts" with passing tests
    And files containing "src/module.ts" with implementation code
    When send_pulse is called with all three files
    Then a PulseResult is returned with exit_code 0
    And the result h_executed reflects all three filenames
    And workspace contains package.json with type module
    And workspace contains vitest.config.ts configuration

  Scenario: Send pulse when vitest fails to produce JSON output
    Given a TypeScriptRunner instance with a running container
    And files containing malformed TypeScript that prevents vitest from running
    When send_pulse is called with the files dictionary
    Then a PulseResult is returned with exit_code 1
    And the result indicates test failure
    And the result bandit_clean is True