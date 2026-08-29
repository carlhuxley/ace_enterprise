Feature: Semantic Code Analyzer detects insecure coding patterns

  Scenario: Detecting SQL string concatenation
    Given the following code snippet:
      """
      q="SELECT * FROM t WHERE x="+x
      """
    When the code is analyzed
    Then the analysis reports 1 issue
    And the issue has type "sql_concatenation"
    And the issue has severity "critical"
    And the issue is reported at line 1, column 29
    And the issue context is "\"SELECT * FROM t WHERE x=\" + x"

  Scenario: Detecting eval() usage
    Given the following code snippet:
      """
      result = eval(user_input)
      """
    When the code is analyzed
    Then the analysis reports 1 issue
    And the issue has type "eval_usage"
    And the issue has severity "critical"
    And the issue is reported at line 1, column 10
    And the issue context is "user_input"

  Scenario: Detecting exec() usage
    Given the following code snippet:
      """
      os_result = exec(command_str)
      """
    When the code is analyzed
    Then the analysis reports 1 issue
    And the issue has type "exec_usage"
    And the issue has severity "critical"
    And the issue is reported at line 1, column 13
    And the issue context is "command_str"

  Scenario: Detecting a hardcoded secret
    Given the following code snippet:
      """
      api_key = "sk_live_938a"
      """
    When the code is analyzed
    Then the analysis reports 1 issue
    And the issue has type "hardcoded_secret"
    And the issue has severity "high"
    And the issue is reported at line 1, column 9
    And the issue context is "sk_live_938a"

  Scenario: Safe code produces no issues
    Given the following code snippet:
      """
      def greet(name):
          return f'Hello, {name}!'
      """
    When the code is analyzed
    Then the analysis reports 0 issues

  Scenario: Detecting multiple distinct vulnerability types in one analysis
    Given the following code snippet:
      """
      q="SELECT * FROM t WHERE x="+x
      result = eval(user_input)
      os_result = exec(command_str)
      """
    When the code is analyzed
    Then the analysis reports 3 issues
    And the issues include a "sql_concatenation" issue
    And the issues include an "eval_usage" issue
    And the issues include an "exec_usage" issue
    And the issues do not include a "hardcoded_secret" issue