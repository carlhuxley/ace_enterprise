Feature: Import Path Validator for Generated Code
  As a caller processing LLM-generated Python code
  I want to validate and correct "src.*" import paths against the actual project layout
  So that generated code references real modules

  Scenario: External (non-src) imports are always considered valid
    Given a project rooted at "/project" with no "src" directory
    And a code snippet "import os\nfrom requests import get"
    When I validate the code
    Then the import "requests" is reported as valid
    And no correction suggestion is given for "requests"

  Scenario: A src import pointing to an existing module file is valid
    Given a project rooted at "/project" containing the file "src/utils/llm_client.py"
    And a code snippet "from src.utils.llm_client import LLMClient"
    When I validate the code
    Then the import "src.utils.llm_client" is reported as valid
    And no correction suggestion is given

  Scenario: A src import pointing to an existing package is valid
    Given a project rooted at "/project" containing the file "src/utils/__init__.py"
    And a code snippet "from src.utils import helper"
    When I validate the code
    Then the import "src.utils" is reported as valid

  Scenario: An invalid src import with a matching module elsewhere yields a suggestion
    Given a project rooted at "/project" containing the file "src/core/llm_client.py"
    And no file exists at "src/utils/llm_client.py"
    And a code snippet "from src.utils.llm_client import LLMClient"
    When I validate the code
    Then the import "src.utils.llm_client" is reported as invalid
    And the suggested correction is "src.core.llm_client"

  Scenario: An invalid src import with no matching module yields no suggestion
    Given a project rooted at "/project" with a "src" directory containing no file named "missing_module.py"
    And a code snippet "from src.foo.missing_module import Thing"
    When I validate the code
    Then the import "src.foo.missing_module" is reported as invalid
    And no correction suggestion is given

  Scenario: Automatically fixing invalid imports rewrites the code and reports corrections
    Given a project rooted at "/project" containing the file "src/core/llm_client.py"
    And a code snippet "from src.utils.llm_client import LLMClient"
    When I call validate_and_fix on the code with auto_fix enabled
    Then the returned code contains "from src.core.llm_client import LLMClient"
    And the returned corrections list contains ("src.utils.llm_client", "src.core.llm_client")

  Scenario: Validating with auto_fix disabled raises an error listing invalid imports
    Given a project rooted at "/project" with a "src" directory containing no file named "missing_module.py"
    And a code snippet "from src.foo.missing_module import Thing"
    When I call validate_and_fix on the code with auto_fix disabled
    Then an ImportValidationError is raised
    And its message mentions "src.foo.missing_module (no suggestion found)"

  Scenario: Code with a syntax error yields no extracted imports and no errors
    Given a project rooted at "/project"
    And a code snippet "def broken(:\n    pass"
    When I validate the code
    Then the validation result list is empty