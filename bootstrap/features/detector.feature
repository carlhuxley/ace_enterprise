Feature: Project Detection and Analysis
  As a developer using the project detector
  I want to detect and analyze Python project structure
  So that I can understand the project layout and configuration

  Scenario: Detect project with pyproject.toml marker
    Given a directory "/tmp/myproject" exists
    And a file "/tmp/myproject/pyproject.toml" exists with content:
      """
      [tool.poetry]
      name = "my-awesome-project"
      """
    When I create a ProjectDetector with startPath "/tmp/myproject"
    And I call detect()
    Then the returned ProjectInfo has root "/tmp/myproject"
    And the returned ProjectInfo has name "my-awesome-project"
    And the returned ProjectInfo has projectType "package"

  Scenario: Detect project with setup.py marker
    Given a directory "/tmp/testproj" exists
    And a file "/tmp/testproj/setup.py" exists with content:
      """
      setup(name="test-project")
      """
    When I create a ProjectDetector with startPath "/tmp/testproj"
    And I call detect()
    Then the returned ProjectInfo has root "/tmp/testproj"
    And the returned ProjectInfo has name "test-project"
    And the returned ProjectInfo has projectType "package"

  Scenario: Detect project root by walking up from subdirectory
    Given a directory "/tmp/parent/child/grandchild" exists
    And a file "/tmp/parent/pyproject.toml" exists
    When I create a ProjectDetector with startPath "/tmp/parent/child/grandchild"
    And I call detect()
    Then the returned ProjectInfo has root "/tmp/parent"

  Scenario: Detect source directory in src layout
    Given a directory "/tmp/proj" exists
    And a file "/tmp/proj/pyproject.toml" exists
    And a directory "/tmp/proj/src" exists
    And a file "/tmp/proj/src/__init__.py" exists
    When I create a ProjectDetector with startPath "/tmp/proj"
    And I call detect()
    Then the returned ProjectInfo has srcDir "/tmp/proj/src"

  Scenario: Detect test directory
    Given a directory "/tmp/proj" exists
    And a file "/tmp/proj/pyproject.toml" exists
    And a directory "/tmp/proj/tests" exists
    When I create a ProjectDetector with startPath "/tmp/proj"
    And I call detect()
    Then the returned ProjectInfo has testDir "/tmp/proj/tests"

  Scenario: Detect git repository
    Given a directory "/tmp/proj" exists
    And a file "/tmp/proj/pyproject.toml" exists
    And a directory "/tmp/proj/.git" exists
    When I create a ProjectDetector with startPath "/tmp/proj"
    And I call detect()
    Then the returned ProjectInfo has hasGit True

  Scenario: Detect Python version from .python-version file
    Given a directory "/tmp/proj" exists
    And a file "/tmp/proj/pyproject.toml" exists
    And a file "/tmp/proj/.python-version" exists with content "3.9.5"
    When I create a ProjectDetector with startPath "/tmp/proj"
    And I call detect()
    Then the returned ProjectInfo has pythonVersion "3.9.5"

  Scenario: Detect package manager as poetry
    Given a directory "/tmp/proj" exists
    And a file "/tmp/proj/pyproject.toml" exists
    And a file "/tmp/proj/poetry.lock" exists
    When I create a ProjectDetector with startPath "/tmp/proj"
    And I call detect()
    Then the returned ProjectInfo has packageManager "poetry"

  Scenario: Detect package manager as pip
    Given a directory "/tmp/proj" exists
    And a file "/tmp/proj/requirements.txt" exists
    When I create a ProjectDetector with startPath "/tmp/proj"
    And I call detect()
    Then the returned ProjectInfo has packageManager "pip"

  Scenario: Detect application type project with main.py
    Given a directory "/tmp/app" exists
    And a file "/tmp/app/main.py" exists
    When I create a ProjectDetector with startPath "/tmp/app"
    And I call detect()
    Then the returned ProjectInfo has projectType "application"

  Scenario: Ensure directories creates missing structure
    Given a directory "/tmp/proj" exists
    And a file "/tmp/proj/pyproject.toml" exists
    And a ProjectDetector with startPath "/tmp/proj"
    And I call detect() returning projectInfo
    When I call ensureDirectories with projectInfo
    Then directory "/tmp/proj/tests" exists
    And file "/tmp/proj/tests/__init__.py" exists
    And directory "/tmp/proj/.ace" exists
    And directory "/tmp/proj/.ace/decisions" exists

  Scenario: Default to current directory when no project markers found
    Given a directory "/tmp/empty" exists with no project markers
    When I create a ProjectDetector with startPath "/tmp/empty"
    And I call detect()
    Then the returned ProjectInfo has root "/tmp/empty"
    And the returned ProjectInfo has name "empty"