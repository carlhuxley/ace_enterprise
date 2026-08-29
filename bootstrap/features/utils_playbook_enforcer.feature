Feature: Playbook enforcement of high-frequency feedback rules

  Scenario: First edit allowed when no session log exists
    Given no session log file exists at the configured path
    When the caller checks if editing "src/app.py" is allowed
    Then the result is allowed
    And the reason is "No session log, first edit allowed"

  Scenario: First edit allowed when session log is empty
    Given the session log file exists and contains an empty list of entries
    When the caller checks if editing "src/app.py" is allowed
    Then the result is allowed
    And the reason is "Empty session log, first edit allowed"

  Scenario: Edit allowed after a tested edit within the allowed ratio
    Given the session log contains 2 "edit" entries and 2 "test" entries
    And the last entry in the log is of type "test"
    When the caller checks if editing "src/app.py" is allowed
    Then the result is allowed
    And the reason is "Previous edit was tested"

  Scenario: Edit blocked when the edit-to-test ratio exceeds the maximum
    Given the enforcer is configured with a max ratio of 2.0
    And the session log contains 5 "edit" entries and 1 "test" entry
    When the caller checks if editing "src/app.py" is allowed
    Then the result is not allowed
    And the reason is "Ratio too high: 5.0 edits/test (max: 2.0) - run more tests (ace-006)"

  Scenario: Edit blocked when the last entry was an untested edit
    Given the session log contains entries where the last entry is of type "edit" for file "src/other.py"
    And the edit-to-test ratio is within the allowed maximum
    When the caller checks if editing "src/app.py" is allowed
    Then the result is not allowed
    And the reason is "Untested edit: src/other.py - run tests first (ace-006)"

  Scenario: Session statistics report zero values when no session log exists
    Given no session log file exists at the configured path
    When the caller requests the current session statistics
    Then the reported edits count is 0
    And the reported tests count is 0
    And the reported ratio is 0.0

  Scenario: Session statistics report computed edit-to-test ratio
    Given the session log contains 4 "edit" entries and 2 "test" entries
    When the caller requests the current session statistics
    Then the reported edits count is 4
    And the reported tests count is 2
    And the reported ratio is 2.0

  Scenario: Session statistics report zero ratio when there are edits but no tests
    Given the session log contains 3 "edit" entries and 0 "test" entries
    When the caller requests the current session statistics
    Then the reported edits count is 3
    And the reported tests count is 0
    And the reported ratio is 0.0