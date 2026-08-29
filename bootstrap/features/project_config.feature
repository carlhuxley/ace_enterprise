Feature: ACE project configuration management

  Scenario: Creating default configuration for a new project
    When a default ACEConfig is created with project_name "acme-api" and project_domain "fintech"
    Then the config has project_name "acme-api"
    And the config has project_domain "fintech"
    And the config has playbooks equal to ["global"]
    And the config has use_central_knowledge equal to True
    And the config has test_framework "pytest"
    And the config has auto_commit equal to False

  Scenario: Checking whether ACE configuration exists for a fresh project
    Given a project root directory with no ".ace" subdirectory
    When exists is called on the project configuration
    Then it returns False

  Scenario: Initializing ACE for a project creates config and supporting files
    Given a project root directory with no ".ace" subdirectory
    When initialize is called with project_name "widget-service"
    Then a ".ace/config.yml" file is created under the project root
    And a ".ace/decisions" directory is created under the project root
    And a ".ace/README.md" file is created mentioning "widget-service"
    And the returned ACEConfig has project_name "widget-service"
    And exists now returns True for the project configuration

  Scenario: Initializing ACE twice for the same project fails
    Given a project root directory where ACE has already been initialized with project_name "widget-service"
    When initialize is called again with project_name "widget-service"
    Then a ValueError is raised

  Scenario: Overrides passed to initialize are applied to the saved configuration
    Given a project root directory with no ".ace" subdirectory
    When initialize is called with project_name "billing-svc" and auto_stage set to True
    Then the returned ACEConfig has auto_stage equal to True
    And loading the configuration from disk also has auto_stage equal to True

  Scenario: Saving and loading a configuration round-trips its values
    Given an ACEConfig with project_name "reporting", test_framework "unittest", and tdd_cycles 5
    When the config is saved to a YAML file and then loaded from that same file
    Then the loaded config has project_name "reporting"
    And the loaded config has test_framework "unittest"
    And the loaded config has tdd_cycles equal to 5

  Scenario: Loading configuration when none exists raises an error
    Given a project root directory with no ".ace" subdirectory
    When load is called on the project configuration
    Then a FileNotFoundError is raised

  Scenario: get_or_create returns existing configuration without overwriting it
    Given a project root directory where ACE has already been initialized with project_name "original-name"
    When get_or_create is called with project_name "ignored-name"
    Then the returned ACEConfig has project_name "original-name"