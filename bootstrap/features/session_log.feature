Feature: Session Log

  Scenario: Create a new session log with default file path
    Given a new SessionLog is created without specifying a log file
    When getEntries is called
    Then it returns an empty list

  Scenario: Create a new session log with custom file path
    Given a new SessionLog is created with log file path "custom_log.json"
    When getEntries is called
    Then it returns an empty list

  Scenario: Log a file edit
    Given a new SessionLog is created
    When logEdit is called with file "main.py" and description "Added new function"
    And getEntries is called
    Then it returns a list with 1 entry
    And the entry has type "edit"
    And the entry has file "main.py"
    And the entry has description "Added new function"
    And the entry has a timestamp field

  Scenario: Log multiple edits and retrieve them
    Given a new SessionLog is created
    When logEdit is called with file "app.py" and description "Fixed bug"
    And logEdit is called with file "test.py" and description "Added tests"
    And getEntries is called
    Then it returns a list with 2 entries

  Scenario: Log a passing test run
    Given a new SessionLog is created
    When logTest is called with testFile "test_feature.py", passed True, and count 5
    And getEntries is called
    Then it returns a list with 1 entry
    And the entry has type "test"
    And the entry has file "test_feature.py"
    And the entry has passed True
    And the entry has count 5
    And the entry has a timestamp field

  Scenario: Log a failing test run
    Given a new SessionLog is created
    When logTest is called with testFile "test_module.py", passed False, and count 3
    And getEntries is called
    Then it returns a list with 1 entry
    And the entry has passed False

  Scenario: Get summary with no entries
    Given a new SessionLog is created
    When getSummary is called
    Then it returns a dict with edits 0
    And testsRun 0
    And testsPassed 0

  Scenario: Get summary with mixed edits and tests
    Given a new SessionLog is created
    When logEdit is called with file "file1.py" and description "Change 1"
    And logEdit is called with file "file2.py" and description "Change 2"
    And logTest is called with testFile "test1.py", passed True, and count 3
    And logTest is called with testFile "test2.py", passed False, and count 2
    And logTest is called with testFile "test3.py", passed True, and count 5
    And getSummary is called
    Then it returns a dict with edits 2
    And testsRun 3
    And testsPassed 2