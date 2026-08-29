Feature: Go Step Definition Generator
  As a developer migrating Gherkin specifications from Python to Go
  I want to generate Go/Cucumber scaffolding from feature files
  So that I can implement and verify behavior in Go

  Scenario: Generate Go step definitions from a feature file with unique steps
    Given a feature file "login.feature" containing:
      """
      Feature: Login
        Scenario: Successful login
          Given a user with username 'alice'
          When the user submits valid credentials
          Then the user is redirected to the dashboard
      """
    And a GoStepGenerator initialized with package name "steps"
    When I call generate_from_feature_file with the feature path and an output directory "gen/"
    Then a file named "login_steps.go" is created in "gen/"
    And the file contains the package declaration "package steps"
    And the file contains a step registration for "a user with username 'alice'"
    And the file contains a step registration for "the user submits valid credentials"
    And the file contains a step registration for "the user is redirected to the dashboard"

  Scenario: Duplicate steps across scenarios are only scaffolded once
    Given a feature file "cart.feature" containing two scenarios that both use the step "Given the cart is empty"
    And a GoStepGenerator initialized with package name "steps"
    When I call generate_from_feature_file with the feature path and an output directory "gen/"
    Then the generated Go file contains exactly one step registration for "the cart is empty"

  Scenario: Quoted values in a step are converted into a matching pattern and function parameters
    Given a feature file "signup.feature" containing the step "Given a user with email 'bob@example.com' and role 'admin'"
    And a GoStepGenerator initialized with package name "steps"
    When I call generate_from_feature_file with the feature path and an output directory "gen/"
    Then the generated Go file contains a step function accepting two string parameters
    And the step function body references parameter values "bob@example.com" and "admin"

  Scenario: Output directory is created automatically if it does not exist
    Given a feature file "checkout.feature" with at least one Given/When/Then step
    And an output directory "build/go_out/" that does not exist
    When I call generate_from_feature_file with the feature path and that output directory
    Then the output directory "build/go_out/" is created
    And the generated Go file is written inside it

  Scenario: Generate a Go test runner for a feature
    Given a GoStepGenerator initialized with package name "steps"
    When I call generate_test_runner with output directory "gen/" and feature name "checkout"
    Then a file named "checkout_test.go" is created in "gen/"
    And the file contains a TestFeatures function that runs a godog test suite
    And the file references the "steps" package

  Scenario: Generate a go.mod file for the output module
    Given a GoStepGenerator initialized with package name "steps"
    When I call generate_go_mod with output directory "gen/" and module name "example.com/checkout"
    Then a file named "go.mod" is created in "gen/"
    And the file declares "module example.com/checkout"
    And the file requires the "github.com/cucumber/godog" dependency

  Scenario: Generate a README describing implementation status
    Given a GoStepGenerator initialized with package name "steps"
    When I call generate_readme with output directory "gen/" and feature name "checkout"
    Then a file named "README.md" is created in "gen/"
    And the README title is "Checkout - Go Implementation"
    And the README lists setup instructions and next steps for implementing the scaffolded step functions