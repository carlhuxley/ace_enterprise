Feature: Playbook Enforcer
  Enforces high-frequency feedback rules by checking edit-to-test ratios and requiring tests after edits

  Scenario: First edit when no session log exists
    Given no session log file exists
    When I check if I can edit "src/main.py"
    Then the edit is allowed
    And the reason is "No session log, first edit allowed"

  Scenario: First edit when session log is empty
    Given an empty session log file exists
    When I check if I can edit "src/main.py"
    Then the edit is allowed
    And the reason is "Empty session log, first edit allowed"

  Scenario: Edit is blocked when last entry was an untested edit
    Given a session log with entries:
      | type | file        |
      | test | testFoo.py |
      | edit | src/foo.py  |
    When I check if I can edit "src/bar.py"
    Then the edit is not allowed
    And the reason is "Untested edit: src/foo.py - run tests first (ace-006)"

  Scenario: Edit is allowed when last entry was a test
    Given a session log with entries:
      | type | file        |
      | edit | src/foo.py  |
      | test | testFoo.py |
    When I check if I can edit "src/bar.py"
    Then the edit is allowed
    And the reason is "Previous edit was tested"

  Scenario: Edit is blocked when edit-to-test ratio exceeds maximum
    Given a PlaybookEnforcer with maxRatio 2.0
    And a session log with entries:
      | type | file         |
      | test | testA.py    |
      | edit | src/a.py     |
      | edit | src/b.py     |
      | test | testB.py    |
      | edit | src/c.py     |
      | edit | src/d.py     |
      | edit | src/e.py     |
    When I check if I can edit "src/f.py"
    Then the edit is not allowed
    And the reason contains "Ratio too high: 2.5 edits/test (max: 2.0) - run more tests (ace-006)"

  Scenario: Get statistics with no session log
    Given no session log file exists
    When I get stats
    Then the stats show 0 edits, 0 tests, and ratio 0.0

  Scenario: Get statistics from existing session log
    Given a session log with entries:
      | type | file        |
      | edit | src/a.py    |
      | test | testA.py   |
      | edit | src/b.py    |
      | test | testB.py   |
      | edit | src/c.py    |
      | edit | src/d.py    |
    When I get stats
    Then the stats show 4 edits, 2 tests, and ratio 2.0

  Scenario: Custom max ratio allows higher edit-to-test ratios
    Given a PlaybookEnforcer with maxRatio 5.0
    And a session log with entries:
      | type | file        |
      | test | testA.py   |
      | edit | src/a.py    |
      | edit | src/b.py    |
      | edit | src/c.py    |
      | edit | src/d.py    |
    When I check if I can edit "src/e.py"
    Then the edit is not allowed
    And the reason is "Untested edit: src/d.py - run tests first (ace-006)"