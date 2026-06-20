Feature: Semantic Code Analyzer

  Scenario: Analyzing code with no security issues
    Given a SemanticCodeAnalyzer instance
    When analyze is called with code "x = 5\ny = 10\nz = x + y"
    Then the result should be an empty list

  Scenario: Detecting SQL concatenation vulnerability
    Given a SemanticCodeAnalyzer instance
    When analyze is called with code "query = 'SELECT * FROM users WHERE id=' + user_id"
    Then the result should contain 1 issue
    And the issue at index 0 should have type "sql_concatenation"
    And the issue at index 0 should have severity "critical"
    And the issue at index 0 should have line 1
    And the issue at index 0 should have column 41

  Scenario: Detecting eval usage vulnerability
    Given a SemanticCodeAnalyzer instance
    When analyze is called with code "result = eval(user_input)"
    Then the result should contain 1 issue
    And the issue at index 0 should have type "eval_usage"
    And the issue at index 0 should have severity "critical"
    And the issue at index 0 should have line 1
    And the issue at index 0 should have column 10

  Scenario: Detecting exec usage vulnerability
    Given a SemanticCodeAnalyzer instance
    When analyze is called with code "exec(dynamic_code)"
    Then the result should contain 1 issue
    And the issue at index 0 should have type "exec_usage"
    And the issue at index 0 should have severity "critical"
    And the issue at index 0 should have line 1
    And the issue at index 0 should have column 1

  Scenario: Detecting hardcoded secret
    Given a SemanticCodeAnalyzer instance
    When analyze is called with code "api_key = \"sk_live_1234567890abcdef\""
    Then the result should contain 1 issue
    And the issue at index 0 should have type "hardcoded_secret"
    And the issue at index 0 should have severity "high"
    And the issue at index 0 should have line 1
    And the issue at index 0 should have column 11
    And the issue at index 0 should have context "sk_live_1234567890abcdef"

  Scenario: Detecting multiple vulnerabilities in multi-line code
    Given a SemanticCodeAnalyzer instance
    When analyze is called with code "password = \"MyP@ssw0rd123\"\nquery = \"DELETE FROM logs WHERE id=\" + log_id\neval(command)"
    Then the result should contain 3 issues
    And the issue at index 0 should have type "hardcoded_secret"
    And the issue at index 0 should have line 1
    And the issue at index 1 should have type "sql_concatenation"
    And the issue at index 1 should have line 2
    And the issue at index 2 should have type "eval_usage"
    And the issue at index 2 should have line 3

  Scenario: SQL concatenation with INSERT statement
    Given a SemanticCodeAnalyzer instance
    When analyze is called with code "sql = 'INSERT INTO users VALUES (' + values + ')'"
    Then the result should contain 1 issue
    And the issue at index 0 should have type "sql_concatenation"
    And the issue at index 0 should have severity "critical"

  Scenario: Short string assignment does not trigger secret detection
    Given a SemanticCodeAnalyzer instance
    When analyze is called with code "name = \"John123\""
    Then the result should be an empty list