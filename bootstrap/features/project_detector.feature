Feature: Python project detection and analysis

  Scenario: Detecting a Poetry-based package project
    Given a directory containing a "pyproject.toml" file with a "[tool.poetry]" section named "my-lib"
    And the directory also contains a "poetry.lock" file
    And the directory contains a ".git" directory
    And the directory contains a "src" subdirectory with a "__init__.py" file
    When the detector detects the project starting from that directory
    Then the returned project name is "my-lib"
    And the returned project type is "package"
    And the returned package manager is "poetry"
    And the returned has_git flag is true
    And the returned source directory is the "src" subdirectory

  Scenario: Detecting a plain script directory with no project markers
    Given an empty directory with no "setup.py", "pyproject.toml", "requirements.txt", ".git", "Pipfile", or "poetry.lock"
    When the detector detects the project starting from that directory
    Then the returned project root is that directory
    And the returned project type is "script"
    And the returned has_git flag is false
    And the returned package manager is None
    And the returned source directory is the project root

  Scenario: Detecting a pip-based application project
    Given a directory containing a "requirements.txt" file
    And the directory contains a "main.py" file
    And the directory contains a "tests" subdirectory
    When the detector detects the project starting from that directory
    Then the returned project type is "application"
    And the returned package manager is "pip"
    And the returned test directory is the "tests" subdirectory

  Scenario: Finding the project root by walking up from a nested subdirectory
    Given a directory tree where the top-level directory contains a "setup.py" file
    And detection starts from a subdirectory several levels below the top-level directory
    When the detector detects the project starting from that subdirectory
    Then the returned project root is the top-level directory containing "setup.py"

  Scenario: Extracting project name from setup.py when pyproject.toml is absent
    Given a directory containing a "setup.py" file with the line 'name="widget-tool"'
    And no "pyproject.toml" file is present
    When the detector detects the project starting from that directory
    Then the returned project name is "widget-tool"

  Scenario: Falling back to directory name when no name can be determined
    Given a directory named "standalone-app" containing only a ".git" directory
    When the detector detects the project starting from that directory
    Then the returned project name is "standalone-app"

  Scenario: Detecting Python version from a .python-version file
    Given a directory containing a ".python-version" file with contents "3.11.4"
    When the detector detects the project starting from that directory
    Then the returned python version is "3.11.4"

  Scenario: Ensuring required directories are created for a detected project
    Given a detected project whose source directory, test directory, and ACE directory do not yet exist on disk
    And the project type is "package"
    When ensure_directories is called with that project's information
    Then the source directory now exists and contains an "__init__.py" file
    And the test directory now exists and contains an "__init__.py" file
    And the ACE directory now exists
    And a "decisions" subdirectory now exists inside the ACE directory