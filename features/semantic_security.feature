Feature: Semantic Code Security Analysis
  As a system administrator
  I want to detect security vulnerabilities in code using AST analysis
  So that I can prevent eval, exec, SQL injection, and hardcoded secrets

  Background:
    Given the SemanticCodeAnalyzer is initialized

  Scenario: Detect security issues in code
    Given the following Python code:
      """
      def execute_query(user_input):
          query = "SELECT * FROM users WHERE name = '" + user_input + "'"
          eval(user_input)
          exec(compile(user_input, '<string>', 'exec'))
          password = "hardcoded_secret_123"
          return query
      """
    When I analyze the code for security issues
    Then the analyzer should detect issue "sql_concatenation" with severity "critical"
    And the analyzer should detect issue "eval_usage" with severity "critical"
    And the analyzer should detect issue "exec_usage" with severity "critical"
    And the analyzer should detect issue "hardcoded_secret" with severity "high"
    And the total security penalty should be at least -30 points
