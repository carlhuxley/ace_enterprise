Feature: Import Filter

  Scenario: Check code with no imports passes validation
    Given an ImportFilter with default settings
    When checking code "x = 1 + 2"
    Then no exception is raised

  Scenario: Check code with allowed import passes validation
    Given an ImportFilter with default settings
    When checking code "import json"
    Then no exception is raised

  Scenario: Check code with blocked import raises ForbiddenImportError
    Given an ImportFilter with default settings
    When checking code "import os"
    Then ForbiddenImportError is raised with message "Forbidden import: os"

  Scenario: Check code with blocked submodule import raises ForbiddenImportError
    Given an ImportFilter with default settings
    When checking code "import os.path"
    Then ForbiddenImportError is raised with message "Forbidden import: os.path"

  Scenario: Check code with blocked from-import raises ForbiddenImportError
    Given an ImportFilter with default settings
    When checking code "from subprocess import run"
    Then ForbiddenImportError is raised with message "Forbidden import: from subprocess"

  Scenario: Check code with blocked builtin call raises ForbiddenImportError
    Given an ImportFilter with default settings
    When checking code "eval('1 + 1')"
    Then ForbiddenImportError is raised with message "Forbidden builtin call: eval()"

  Scenario: Check code with blocked exec call raises ForbiddenImportError
    Given an ImportFilter with default settings
    When checking code "exec('x = 1')"
    Then ForbiddenImportError is raised with message "Forbidden builtin call: exec()"

  Scenario: Check code with invalid syntax raises SyntaxError
    Given an ImportFilter with default settings
    When checking code "import os if"
    Then SyntaxError is raised

  Scenario: Check code with custom blocklist blocks specified module
    Given an ImportFilter with blocklist ["requests"]
    When checking code "import requests"
    Then ForbiddenImportError is raised with message "Forbidden import: requests"

  Scenario: Check code with custom blocklist allows default blocked modules
    Given an ImportFilter with blocklist ["requests"]
    When checking code "import os"
    Then no exception is raised

  Scenario: Check code with custom blocked builtins blocks specified builtin
    Given an ImportFilter with blocked_builtins ["open"]
    When checking code "open('file.txt')"
    Then ForbiddenImportError is raised with message "Forbidden builtin call: open()"

  Scenario: Check code with custom blocked builtins allows default blocked builtins
    Given an ImportFilter with blocked_builtins ["open"]
    When checking code "eval('1 + 1')"
    Then no exception is raised

  Scenario: Check code with multiple blocked imports detects first violation
    Given an ImportFilter with default settings
    When checking code "import json\nimport socket\nimport sys"
    Then ForbiddenImportError is raised with message "Forbidden import: socket"