Feature: Project Configuration
  Manages per-project ACE configuration including creation, persistence, and loading

  Scenario: Create default config with project name
    Given a project name "my-project"
    When a default config is created
    Then the config has project_name "my-project"
    And the config has a non-empty test_framework field

  Scenario: Convert config to dictionary and back
    Given a config with project_name "test-proj" and tdd_cycles 5
    When the config is serialised to a dictionary
    And a new config is deserialised from that dictionary
    Then the new config has project_name "test-proj"
    And the new config has tdd_cycles 5

  Scenario: Check exists returns false for uninitialised project
    Given a project directory with no ACE configuration
    When exists is called on the project config manager
    Then false is returned

  Scenario: Initialise creates config and exists returns true
    Given a project directory with no ACE configuration
    When the project is initialised with project_name "new-project"
    Then exists returns true
    And loading the config returns project_name "new-project"

  Scenario: Get-or-create returns existing config unchanged
    Given a project directory already initialised with project_name "existing-project"
    When get_or_create is called with project_name "other-name"
    Then the returned config has project_name "existing-project"
