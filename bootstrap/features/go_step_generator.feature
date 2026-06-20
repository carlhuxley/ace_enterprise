Feature: Go Step Definition Generator
  As a developer migrating Python code to Go
  I want to generate Go step definitions from Gherkin feature files
  So that I can implement the same behavior in Go

  Scenario: Generate Go step definitions from a simple feature file
    Given a feature file "simple.feature" with content:
      """
      Feature: Simple Feature
        Scenario: Basic scenario
          Given a user named 'Alice'
          When the user logs in
          Then the user should see 'Welcome'
      """
    And a GoStepGenerator with package name "steps"
    When I call generate_from_feature_file with the feature file and output directory "/tmp/output"
    Then a Go file "/tmp/output/simple_steps.go" is created
    And the Go file contains "package steps"
    And the Go file contains "type SimpleContext struct"
    And the Go file contains "func (ctx *SimpleContext) aUserNamed(param1 string) error"
    And the Go file contains "func (ctx *SimpleContext) theUserLogsIn() error"
    And the Go file contains "func (ctx *SimpleContext) theUserShouldSee(param1 string) error"

  Scenario: Handle And and But steps by inheriting previous step type
    Given a feature file "chained.feature" with content:
      """
      Feature: Chained Steps
        Scenario: Using And
          Given a user exists
          And the user is active
          When the user logs in
          And the session is created
          Then the user is authenticated
          But the user cannot access admin
      """
    And a GoStepGenerator with package name "steps"
    When I call generate_from_feature_file with the feature file and output directory "/tmp/output"
    Then the generated Go file contains step registrations for all unique steps
    And And steps are treated as the same type as their preceding step

  Scenario: Extract parameters from quoted strings in steps
    Given a feature file "params.feature" with content:
      """
      Feature: Parameters
        Scenario: With quotes
          Given a user with email 'alice@example.com'
          When I send a message "Hello World"
          Then the response contains 'success'
      """
    And a GoStepGenerator with package name "steps"
    When I call generate_from_feature_file with the feature file and output directory "/tmp/output"
    Then the Go file contains "func (ctx *ParamsContext) aUserWithEmail(param1 string) error"
    And the Go file contains "func (ctx *ParamsContext) iSendAMessage(param1 string) error"
    And the step regex patterns capture quoted string values

  Scenario: Extract numeric parameters from steps
    Given a feature file "numbers.feature" with content:
      """
      Feature: Numbers
        Scenario: With numbers
          Given there are 5 users
          When I wait 30 seconds
      """
    And a GoStepGenerator with package name "steps"
    When I call generate_from_feature_file with the feature file and output directory "/tmp/output"
    Then the Go file contains "func (ctx *NumbersContext) thereAre(num1 string) error"
    And the Go file contains "func (ctx *NumbersContext) iWait(num1 string) error"
    And the step regex patterns capture numeric values

  Scenario: Generate test runner file
    Given a GoStepGenerator with package name "steps"
    When I call generate_test_runner with output directory "/tmp/output" and feature name "oauth"
    Then a Go file "/tmp/output/oauth_test.go" is created
    And the test file contains "package steps_test"
    And the test file contains "func TestFeatures(t *testing.T)"
    And the test file contains "ctx := steps.NewOauthContext(t)"
    And the test file contains "Paths:    []string{\"features\"}"

  Scenario: Generate go.mod file
    Given a GoStepGenerator with package name "steps"
    When I call generate_go_mod with output directory "/tmp/output" and module name "example.com/myapp"
    Then a file "/tmp/output/go.mod" is created
    And the go.mod file contains "module example.com/myapp"
    And the go.mod file contains "go 1.21"
    And the go.mod file contains "github.com/cucumber/godog v0.14.0"

  Scenario: Generate README documentation
    Given a GoStepGenerator with package name "steps"
    When I call generate_readme with output directory "/tmp/output" and feature name "oauth_flow"
    Then a file "/tmp/output/README.md" is created
    And the README contains "# Oauth Flow - Go Implementation"
    And the README contains setup instructions with "go mod download"
    And the README contains "go test -v"
    And the README contains cross-language verification instructions

  Scenario: Remove duplicate steps from feature file
    Given a feature file "duplicates.feature" with content:
      """
      Feature: Duplicates
        Scenario: First
          Given a user exists
          When the user logs in
        Scenario: Second
          Given a user exists
          When the user logs in
      """
    And a GoStepGenerator with package name "steps"
    When I call generate_from_feature_file with the feature file and output directory "/tmp/output"
    Then the Go file contains exactly one definition for "aUserExists"
    And the Go file contains exactly one definition for "theUserLogsIn"