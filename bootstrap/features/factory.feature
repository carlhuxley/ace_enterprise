Feature: Autonomous TDD Agent Factory

  Scenario: Build agent with minimal project configuration
    Given a ProjectConfig with playbook_id "test-project-123"
    And the ProjectConfig has project_root "/home/user/myproject"
    And the ProjectConfig has test_dir "tests"
    And the ProjectConfig has src_dir "src"
    And the ProjectConfig has max_iterations 5
    When build_agent is called with the ProjectConfig
    Then an AutonomousTDDAgent instance is returned
    And the agent has project_root "/home/user/myproject"
    And the agent has test_dir "tests"
    And the agent has src_dir "src"
    And the agent has max_iterations 5

  Scenario: Build agent creates ensemble learner with playbook
    Given a ProjectConfig with playbook_id "my-playbook-456"
    And the ProjectConfig has project_root "/workspace"
    And the ProjectConfig has test_dir "test"
    And the ProjectConfig has src_dir "lib"
    And the ProjectConfig has max_iterations 10
    When build_agent is called with the ProjectConfig
    Then an AutonomousTDDAgent instance is returned
    And the agent's ensemble learner uses playbook_id "my-playbook-456"

  Scenario: Build agent with different playbook identifiers
    Given a ProjectConfig with playbook_id "project-alpha"
    And the ProjectConfig has project_root "/app"
    And the ProjectConfig has test_dir "tests"
    And the ProjectConfig has src_dir "src"
    And the ProjectConfig has max_iterations 3
    When build_agent is called with the ProjectConfig
    Then an AutonomousTDDAgent instance is returned
    And the agent's ensemble learner uses playbook_id "project-alpha"

  Scenario: Build agent with custom iteration limit
    Given a ProjectConfig with playbook_id "iteration-test"
    And the ProjectConfig has project_root "/code"
    And the ProjectConfig has test_dir "tests"
    And the ProjectConfig has src_dir "source"
    And the ProjectConfig has max_iterations 20
    When build_agent is called with the ProjectConfig
    Then an AutonomousTDDAgent instance is returned
    And the agent has max_iterations 20

  Scenario: Build agent with custom directory structure
    Given a ProjectConfig with playbook_id "custom-dirs"
    And the ProjectConfig has project_root "/opt/application"
    And the ProjectConfig has test_dir "spec"
    And the ProjectConfig has src_dir "app"
    And the ProjectConfig has max_iterations 7
    When build_agent is called with the ProjectConfig
    Then an AutonomousTDDAgent instance is returned
    And the agent has project_root "/opt/application"
    And the agent has test_dir "spec"
    And the agent has src_dir "app"

  Scenario: Build agent includes test reviewer component
    Given a ProjectConfig with playbook_id "reviewer-test"
    And the ProjectConfig has project_root "/project"
    And the ProjectConfig has test_dir "tests"
    And the ProjectConfig has src_dir "src"
    And the ProjectConfig has max_iterations 5
    When build_agent is called with the ProjectConfig
    Then an AutonomousTDDAgent instance is returned
    And the agent has a test_reviewer component