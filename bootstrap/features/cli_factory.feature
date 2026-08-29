Feature: Sandboxed TDD run handle for a project

  As a caller of the ace tooling
  I want a TDDRunHandle built for a given project configuration
  So that I can drive a sandboxed RED/GREEN/REFACTOR loop from Gherkin feature files

  Scenario: Building an agent wires the handle to the project's directories
    Given a ProjectConfig with test_dir "tests" and src_dir "src"
    When I call build_agent with that config
    Then the returned TDDRunHandle's test_dir is "tests"
    And the returned TDDRunHandle's src_dir is "src"

  Scenario: Building an agent with skip_learn disabled still succeeds
    Given a ProjectConfig for a project
    When I call build_agent with that config and skip_learn set to False
    Then a TDDRunHandle is returned successfully

  Scenario: Building an agent with skip_learn enabled still succeeds
    Given a ProjectConfig for a project
    When I call build_agent with that config and skip_learn set to True
    Then a TDDRunHandle is returned successfully

  Scenario: Running a TDD build from a feature file without an explicit requirement
    Given a TDDRunHandle with test_dir "tests" and src_dir "src"
    And a Gherkin feature file at "features/calculator.feature" describing calculator behavior
    When I call build_from_feature with that feature path and no requirement
    Then an IterativeResult is returned
    And the requirement used is derived from the feature file's own description

  Scenario: Running a TDD build from a feature file with an explicit requirement override
    Given a TDDRunHandle with test_dir "tests" and src_dir "src"
    And a Gherkin feature file at "features/calculator.feature"
    When I call build_from_feature with that feature path and requirement "Support division with remainder"
    Then an IterativeResult is returned
    And the requirement used is "Support division with remainder" instead of the one derived from the feature file

  Scenario: Resolving file paths for a feature file
    Given a TDDRunHandle with test_dir "tests" and src_dir "src"
    When I call file_paths_for with feature path "features/calculator.feature"
    Then the returned test file path is "tests/test_calculator.py"
    And the returned implementation file path is "src/calculator.py"

  Scenario: Stopping the handle tears down its sandbox
    Given a TDDRunHandle that has been used to run at least one build
    When I call stop on the handle
    Then the underlying sandbox is stopped without raising an error