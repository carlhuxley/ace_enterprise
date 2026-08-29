Feature: ace CLI tdd command
  As a user of the ace CLI
  I want to run TDD builds against a project using a feature file
  So that I can generate tests and implementation code from Gherkin specs

  Scenario: Running tdd against a non-existent project directory
    Given the directory "/tmp/does-not-exist" does not exist
    When I run "ace tdd --project /tmp/does-not-exist"
    Then the command exits with status 1
    And stderr contains "error: project directory not found"

  Scenario: Running tdd with no feature files present and none specified
    Given a project directory with no "features/" directory and no .feature files
    When I run "ace tdd --project <project>"
    Then the command exits with status 1
    And stderr contains "error: no .feature files found"

  Scenario: Running tdd with an explicit feature file that does not exist
    Given a valid project directory "<project>"
    When I run "ace tdd --project <project> --feature missing.feature"
    Then the command exits with status 1
    And stderr contains "error: feature file not found"

  Scenario: Running tdd with a single auto-discovered feature file
    Given a project directory "<project>" containing exactly one file "features/login.feature"
    When I run "ace tdd --project <project>"
    Then stdout shows "Project:" followed by the resolved project path
    And stdout shows "Feature:    features/login.feature"
    And the command builds the feature and exits with status 0 or 1 depending on build success

  Scenario: Running tdd with multiple feature files and none specified
    Given a project directory "<project>" containing "features/login.feature" and "features/logout.feature"
    When I run "ace tdd --project <project>"
    Then stdout contains "Found multiple feature files — building all in sequence:"
    And stdout lists "features/login.feature" and "features/logout.feature"
    And the first discovered feature file is used for the build

  Scenario: Overriding the playbook ID and max iterations
    Given a valid project directory "<project>" with a single feature file
    When I run "ace tdd --project <project> --playbook-id custom-playbook --max-iterations 5"
    Then stdout shows "Playbook:   custom-playbook"
    And the build runs with a maximum of 5 iterations

  Scenario: Skipping the LEARN phase
    Given a valid project directory "<project>" with a single feature file
    When I run "ace tdd --project <project> --no-learn"
    Then the build completes without updating the playbook

  Scenario: Successful build reports completion summary
    Given a valid project directory "<project>" with a single feature file that the agent can satisfy
    When I run "ace tdd --project <project>"
    Then stdout contains "Done — " followed by the number of cycles
    And stdout contains the generated test file path
    And stdout contains the generated implementation file path
    And the command exits with status 0

  Scenario: Running without a subcommand
    When I run "ace" with no arguments
    Then the command exits with a non-zero status due to a missing required subcommand