Feature: ACE Enterprise CLI
  As a developer
  I want to run "ace tdd" against my project
  So that ACE builds features using TDD without manual intervention

  Scenario: Run TDD on a specific feature file
    Given a project directory at "/home/user/myproject" containing src and tests directories
    And a feature file at "/home/user/myproject/features/login.feature" with content "Feature: User Login"
    When the CLI is invoked with args ["tdd", "--project", "/home/user/myproject", "--feature", "features/login.feature"]
    Then the agent is constructed with project_root "/home/user/myproject"
    And build_feature is called with requirement "User Login"
    And the process exits with code 0

  Scenario: Auto-discover feature files from project features directory
    Given a project directory at "/home/user/myproject"
    And a "features/" subdirectory containing "auth.feature"
    When the CLI is invoked with args ["tdd", "--project", "/home/user/myproject"]
    Then build_feature is called using the discovered feature file
    And the process exits with code 0

  Scenario: Exit with error when project directory does not exist
    Given no directory exists at "/nonexistent/project"
    When the CLI is invoked with args ["tdd", "--project", "/nonexistent/project"]
    Then the process exits with code 1
    And stderr contains "project directory not found"

  Scenario: Exit with error when no feature files are discovered
    Given a project directory at "/home/user/empty" with no .feature files
    When the CLI is invoked with args ["tdd", "--project", "/home/user/empty"]
    Then the process exits with code 1
    And stderr contains "no .feature files found"

  Scenario: Load project config from .ace/config.yaml when present
    Given a project directory at "/home/user/myproject"
    And a ".ace/config.yaml" file with max_iterations 5 and playbook_id "my-playbook"
    And a feature file at "/home/user/myproject/features/feature.feature"
    When the CLI is invoked with args ["tdd", "--project", "/home/user/myproject"]
    Then the agent is constructed with max_iterations 5
    And the agent uses playbook_id "my-playbook"

  Scenario: --playbook-id flag overrides config value
    Given a project directory with ".ace/config.yaml" specifying playbook_id "config-playbook"
    And a feature file at "features/feature.feature"
    When the CLI is invoked with args ["tdd", "--project", ".", "--playbook-id", "override-playbook"]
    Then the agent uses playbook_id "override-playbook"

  Scenario: --no-learn flag disables the LEARN phase
    Given a project directory with a feature file at "features/f.feature"
    When the CLI is invoked with args ["tdd", "--project", ".", "--feature", "features/f.feature", "--no-learn"]
    Then the agent is constructed with skip_learn set to true

  Scenario: Extract requirement from Feature line in .feature file
    Given a feature file containing "Feature: Shopping Cart Checkout"
    When the requirement is extracted from the feature file
    Then the extracted requirement is "Shopping Cart Checkout"

  Scenario: Fall back to filename as requirement when no Feature line present
    Given a feature file named "user_auth.feature" with no Feature: line
    When the requirement is extracted from the feature file
    Then the extracted requirement is "user auth"

  Scenario: Print project summary before running
    Given a project directory at "/home/user/myproject" with a feature file
    When the CLI is invoked with args ["tdd", "--project", "/home/user/myproject"]
    Then stdout contains "Project:"
    And stdout contains "Feature:"
    And stdout contains "Playbook:"
