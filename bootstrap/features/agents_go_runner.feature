Feature: GoRunner executes Go test/vet/security pulses in an isolated container

  As a caller of the Go TDD harness
  I want to submit a set of Go source files for evaluation
  So that I receive test results, static analysis findings, and formatted source back

  Scenario: Submitted Go files that pass vet and tests report success
    Given a GoRunner instance for the Go harness container
    When I call send_pulse with files {"main.go": "package main\n\nfunc Add(a, b int) int { return a + b }\n"}
    Then the returned PulseResult has exit_code 0
    And the returned PulseResult's bandit_output reflects the gosec scan of the submitted files

  Scenario: A file that fails "go vet" produces a failing result with a prefixed message
    Given a GoRunner instance for the Go harness container
    When I call send_pulse with files {"main.go": "package main\n\nfunc Add(a, b int) int { return a }\n"}
    And "go vet" reports an error for the submitted code
    Then the returned PulseResult has exit_code 1
    And the returned PulseResult's stdout starts with "go vet failed:"

  Scenario: A file that fails its Go tests produces a failing result
    Given a GoRunner instance for the Go harness container
    When I call send_pulse with files {"main.go": "package main\n\nfunc Add(a, b int) int { return a + b }\n", "main_test.go": "package main\n\nimport \"testing\"\n\nfunc TestAdd(t *testing.T) { if Add(1, 1) != 3 { t.Fail() } }\n"}
    Then the returned PulseResult has exit_code 1
    And the returned PulseResult's stdout does not start with "go vet failed:"

  Scenario: gosec findings are surfaced as severity counts
    Given a GoRunner instance for the Go harness container
    When I call send_pulse with files {"main.go": "package main\n\nimport \"os/exec\"\n\nfunc Run(cmd string) { exec.Command(cmd).Run() }\n"}
    And gosec detects a "G204" issue with severity "MEDIUM" in the submitted code
    Then the returned PulseResult's bandit_high is at least 1
    And the returned PulseResult's bandit_clean is false

  Scenario: Clean code with no security findings reports bandit_clean true
    Given a GoRunner instance for the Go harness container
    When I call send_pulse with files {"main.go": "package main\n\nfunc Add(a, b int) int { return a + b }\n"}
    And gosec reports no issues for the submitted code
    Then the returned PulseResult's bandit_high is 0
    And the returned PulseResult's bandit_medium is 0
    And the returned PulseResult's bandit_low is 0
    And the returned PulseResult's bandit_clean is true

  Scenario: Improperly formatted Go source is returned reformatted by gofmt
    Given a GoRunner instance for the Go harness container
    When I call send_pulse with files {"main.go": "package main\nfunc Add(a,b int) int {return a+b}\n"}
    Then the returned PulseResult's formatted_files contains a key "main.go"
    And the value for "main.go" in formatted_files is the gofmt-reformatted source

  Scenario: Non-Go files submitted alongside Go files are not included in formatted_files
    Given a GoRunner instance for the Go harness container
    When I call send_pulse with files {"main.go": "package main\n\nfunc Add(a, b int) int { return a + b }\n", "README.md": "# notes\n"}
    Then the returned PulseResult's formatted_files does not contain a key "README.md"

  Scenario: A GoRunner can be constructed with custom resource limits and timeout
    Given no running GoRunner container
    When I create a GoRunner with cpus "4", memory "2g", and test_timeout 20
    Then the GoRunner instance is created without error
    And subsequent calls to send_pulse on that instance use the configured resource limits