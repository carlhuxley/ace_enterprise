Feature: Session Log
  Tracks file edits and test runs during a session, persisting entries to a JSON file and providing summary statistics.

  Scenario: Logging a file edit records it as an entry
    Given a new SessionLog using a temporary log file
    When I log an edit for file "src/app.py" with description "refactored parser"
    Then get_entries returns 1 entry
    And the entry has type "edit", file "src/app.py", and description "refactored parser"

  Scenario: Logging a test run records pass/fail and count
    Given a new SessionLog using a temporary log file
    When I log a test run for file "tests/test_app.py" with passed True and count 12
    Then get_entries returns 1 entry
    And the entry has type "test", file "tests/test_app.py", passed True, and count 12

  Scenario: Summary counts edits and test results across multiple entries
    Given a new SessionLog using a temporary log file
    When I log an edit for file "src/a.py" with description "fix bug"
    And I log a test run for file "tests/test_a.py" with passed True and count 5
    And I log a test run for file "tests/test_b.py" with passed False and count 3
    Then get_summary returns edits 1, tests_run 2, and tests_passed 1

  Scenario: Summary on an empty log reports all zeros
    Given a new SessionLog using a temporary log file
    Then get_summary returns edits 0, tests_run 0, and tests_passed 0

  Scenario: Logged entries are persisted to the log file as JSON
    Given a new SessionLog using log file "session.json"
    When I log an edit for file "src/b.py" with description "add feature"
    Then the file "session.json" contains valid JSON with 1 entry
    And the JSON entry has type "edit" and file "src/b.py"

  Scenario: Default log file is used when none is provided
    Given a new SessionLog created without specifying a log file
    When I log an edit for file "src/c.py" with description "cleanup"
    Then the file ".session_log.json" contains valid JSON with 1 entry

  Scenario: Entries accumulate in order across multiple log calls
    Given a new SessionLog using a temporary log file
    When I log an edit for file "src/x.py" with description "first change"
    And I log a test run for file "tests/test_x.py" with passed True and count 1
    And I log an edit for file "src/y.py" with description "second change"
    Then get_entries returns 3 entries
    And the first entry has type "edit" and file "src/x.py"
    And the second entry has type "test" and file "tests/test_x.py"
    And the third entry has type "edit" and file "src/y.py"