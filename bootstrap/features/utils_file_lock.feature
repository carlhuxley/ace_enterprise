Feature: Protecting target files from inadvertent edits during automated changes

  As a developer running an automated code-modification tool
  I want non-target Python files to be locked read-only during the operation
  And any unexpected changes to non-target files to be detected afterward
  So that I can be confident only intended files were modified

  Scenario: Locking makes non-target Python files read-only while the lock is active
    Given a project root containing "src/target.py" and "src/other.py"
    And "src/target.py" is the only file listed as a target
    When I enter a file lock context for "src/target.py" under that project root
    Then "src/other.py" becomes read-only
    And "src/target.py" remains writable

  Scenario: Exiting the lock context restores original file permissions
    Given a project root containing "src/other.py" with mode 0o644
    And "src/other.py" is not in the target file list
    When I enter and then exit a file lock context for a different target file
    Then "src/other.py" is restored to mode 0o644

  Scenario: Files inside __pycache__ directories are not locked
    Given a project root containing "src/__pycache__/cached.py"
    When I enter a file lock context with no matching target files
    Then "src/__pycache__/cached.py" remains writable

  Scenario: Drift detection reports no drift when git shows no changes
    Given a project root with a clean git working tree
    When I check for drift against target files "src/target.py"
    Then the resulting drift report is clean
    And the drifted files list is empty

  Scenario: Drift detection reports changes made to a non-target Python file
    Given a project root where "src/other.py" has uncommitted changes adding 3 lines and removing 1 line
    And "src/other.py" is not in the target file list
    When I check for drift against target files "src/target.py"
    Then the resulting drift report is not clean
    And the drifted files list contains "src/other.py" with 3 added lines and 1 removed line

  Scenario: Drift detection ignores changes made to target files
    Given a project root where "src/target.py" has uncommitted changes
    And "src/target.py" is in the target file list
    When I check for drift against target files "src/target.py"
    Then the resulting drift report is clean

  Scenario: Drift detection ignores changes to non-Python files
    Given a project root where "README.md" has uncommitted changes
    When I check for drift against target files "src/target.py"
    Then the resulting drift report is clean

  Scenario: Asserting cleanliness raises an error listing drifted file paths
    Given a drift report containing drifted files "src/other.py" and "src/utils.py"
    When I assert that the report is clean
    Then an InadvertentDriftError is raised
    And its message mentions "src/other.py" and "src/utils.py"