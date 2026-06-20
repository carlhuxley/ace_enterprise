Feature: Import Path Validator

  Scenario: Extract import statements from valid Python code
    Given a project root directory "/project"
    And an ImportValidator initialized with that project root
    When extractImports is called with code containing "import os" and "from src.utils import helper"
    Then the result contains a tuple ("import", "os")
    And the result contains a tuple ("from", "src.utils")

  Scenario: Extract imports from code with syntax errors
    Given a project root directory "/project"
    And an ImportValidator initialized with that project root
    When extractImports is called with code "from src.utils import ("
    Then the result is an empty list

  Scenario: Validate external import path that does not start with src
    Given a project root directory "/project"
    And an ImportValidator initialized with that project root
    When validateImport is called with "os.path"
    Then the result is (True, None)

  Scenario: Validate correct src import path for existing module file
    Given a project root directory "/project"
    And a file exists at "/project/src/utils/helper.py"
    And an ImportValidator initialized with that project root
    When validateImport is called with "src.utils.helper"
    Then the result is (True, None)

  Scenario: Validate correct src import path for existing package
    Given a project root directory "/project"
    And a file exists at "/project/src/utils/__init__.py"
    And an ImportValidator initialized with that project root
    When validateImport is called with "src.utils"
    Then the result is (True, None)

  Scenario: Validate invalid src import with suggestion from module cache
    Given a project root directory "/project"
    And a file exists at "/project/src/utils/helper.py"
    And an ImportValidator initialized with that project root
    When validateImport is called with "src.wrong.helper"
    Then the result is (False, "src.utils.helper")

  Scenario: Validate invalid src import with no suggestion available
    Given a project root directory "/project"
    And an ImportValidator initialized with that project root
    When validateImport is called with "src.nonexistent.module"
    Then the result is (False, None)

  Scenario: Validate code with all valid imports
    Given a project root directory "/project"
    And a file exists at "/project/src/utils/helper.py"
    And an ImportValidator initialized with that project root
    When validateCode is called with "from src.utils import helper\nimport os"
    Then the result contains ("src.utils", True, None)
    And the result does not contain any invalid imports

  Scenario: Fix imports automatically corrects invalid import paths
    Given a project root directory "/project"
    And a file exists at "/project/src/utils/helper.py"
    And an ImportValidator initialized with that project root
    When fixImports is called with code "from src.wrong import helper"
    Then the fixed code contains "from src.utils.helper import helper"
    And the corrections list contains ("src.wrong", "src.utils.helper")

  Scenario: Validate and fix with autoFix enabled succeeds
    Given a project root directory "/project"
    And a file exists at "/project/src/utils/helper.py"
    And an ImportValidator initialized with that project root
    When validateAndFix is called with code "from src.wrong import helper" and autoFix True
    Then the returned code contains "from src.utils.helper import helper"
    And the corrections list contains ("src.wrong", "src.utils.helper")

  Scenario: Validate and fix with autoFix disabled raises error for invalid imports
    Given a project root directory "/project"
    And an ImportValidator initialized with that project root
    When validateAndFix is called with code "from src.nonexistent import module" and autoFix False
    Then an ImportValidationError is raised
    And the error contains invalid import "src.nonexistent"

  Scenario: Validate and fix raises error when imports cannot be corrected
    Given a project root directory "/project"
    And an ImportValidator initialized with that project root
    When validateAndFix is called with code "from src.nonexistent import module" and autoFix True
    Then an ImportValidationError is raised
    And the error contains invalid import "src.nonexistent"

  Scenario: Validate and fix returns unchanged code when all imports are valid
    Given a project root directory "/project"
    And a file exists at "/project/src/utils/helper.py"
    And an ImportValidator initialized with that project root
    When validateAndFix is called with code "from src.utils import helper" and autoFix True
    Then the returned code is "from src.utils import helper"
    And the corrections list is empty