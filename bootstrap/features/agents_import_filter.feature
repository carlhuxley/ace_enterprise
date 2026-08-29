Feature: Static import and builtin-call filtering
  As a caller embedding untrusted code snippets, I want to statically reject
  code that imports forbidden modules or calls forbidden builtins, so that
  such code never reaches execution.

  Background:
    Given an ImportFilter created with default settings

  Scenario: Safe code with no forbidden imports or calls passes
    When I check the code "import json\nprint(json.dumps({'a': 1}))"
    Then no error is raised

  Scenario: Directly importing a blocklisted module is rejected
    When I check the code "import os"
    Then a ForbiddenImportError is raised with message "Forbidden import: os"

  Scenario: Importing a submodule of a blocklisted root is rejected
    When I check the code "import os.path"
    Then a ForbiddenImportError is raised with message "Forbidden import: os.path"

  Scenario: A from-import of a blocklisted module is rejected
    When I check the code "from subprocess import run"
    Then a ForbiddenImportError is raised with message "Forbidden import: from subprocess"

  Scenario: Calling a blocked builtin is rejected
    When I check the code "eval('1 + 1')"
    Then a ForbiddenImportError is raised with message "Forbidden builtin call: eval()"

  Scenario: Dynamic import of a blocklisted module via __import__ is rejected
    When I check the code "__import__('os')"
    Then a ForbiddenImportError is raised with message "Forbidden dynamic import: os"

  Scenario: Dynamic import via an aliased importlib.import_module call is rejected
    When I check the code "import importlib as il\nil.import_module('socket')"
    Then a ForbiddenImportError is raised with message "Forbidden dynamic import: socket"

  Scenario: Syntactically invalid code raises a SyntaxError instead of a policy violation
    When I check the code "def broken(:"
    Then a SyntaxError is raised

  Scenario: A custom blocklist overrides the default forbidden modules
    Given an ImportFilter created with blocklist {"requests"} and blocked_builtins {}
    When I check the code "import os"
    Then no error is raised