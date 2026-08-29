Feature: Project configuration loading and feature discovery

  Scenario: Loading config when no .ace/config.yaml exists uses defaults
    Given a project root directory with no ".ace/config.yaml" file
    When ProjectConfig.load is called with that project root
    Then the returned config has playbook_scope "both"
    And the returned config has playbook_id equal to the project root directory's name
    And the returned config has promote_threshold 0.85
    And the returned config has max_iterations 20
    And the returned config has team_id None

  Scenario: Loading config reads values from .ace/config.yaml
    Given a project root directory containing ".ace/config.yaml" with:
      """
      playbook: local
      playbook_id: my-project
      promote_threshold: 0.9
      max_iterations: 5
      team_id: team-42
      """
    When ProjectConfig.load is called with that project root
    Then the returned config has playbook_scope "local"
    And the returned config has playbook_id "my-project"
    And the returned config has promote_threshold 0.9
    And the returned config has max_iterations 5
    And the returned config has team_id "team-42"

  Scenario: Loading config with an invalid playbook scope raises an error
    Given a project root directory containing ".ace/config.yaml" with:
      """
      playbook: nonsense
      """
    When ProjectConfig.load is called with that project root
    Then a ValueError is raised mentioning the allowed playbook values and the invalid value "nonsense"

  Scenario: Test and source directories are auto-detected from known candidate names
    Given a project root directory containing a "test" subdirectory and a "lib" subdirectory
    And no ".ace/config.yaml" file
    When ProjectConfig.load is called with that project root
    Then the returned config's test_dir is the "test" subdirectory
    And the returned config's src_dir is the "lib" subdirectory

  Scenario: Test and source directories fall back to defaults when no candidates exist
    Given a project root directory with no "tests", "test", "src", or "lib" subdirectories
    And no ".ace/config.yaml" file
    When ProjectConfig.load is called with that project root
    Then the returned config's test_dir is the project root's "tests" subdirectory
    And the returned config's src_dir is the project root's "src" subdirectory

  Scenario: Discovering feature files prefers a "features" subdirectory
    Given a project root containing a "features" subdirectory with files "a.feature" and "b.feature"
    And the project root itself also contains a "c.feature" file
    When discover_features is called on the config
    Then the result is the sorted list ["features/a.feature", "features/b.feature"]

  Scenario: Discovering feature files falls back to the project root when no "features" subdirectory exists
    Given a project root with no "features" subdirectory
    And the project root contains "x.feature" and "y.feature" files
    When discover_features is called on the config
    Then the result is the sorted list ["x.feature", "y.feature"]

  Scenario: Discovering feature files returns an empty list when none are found
    Given a project root with no "features" subdirectory and no ".feature" files
    When discover_features is called on the config
    Then the result is an empty list