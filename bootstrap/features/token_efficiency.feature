Feature: Token Efficiency Reporter

  Scenario: Score a single pod run with multiple cycles
    Given a pod run for "Python" implementing "User login" with 3 cycles to green
    And cycle 1 used 100 input tokens and 50 output tokens
    And cycle 2 used 120 input tokens and 60 output tokens
    And cycle 3 used 80 input tokens and 40 output tokens
    When the reporter scores the pod runs
    Then the report contains 1 language score
    And the score for "Python" has total input tokens of 300
    And the score for "Python" has total output tokens of 150
    And the score for "Python" has cycles to green of 3
    And the score for "Python" has tokens per green of 150.0
    And the report has no comparison

  Scenario: Score multiple pod runs for different languages and same feature
    Given a pod run for "Python" implementing "Calculator" with 2 cycles to green
    And cycle 1 used 200 input tokens and 100 output tokens
    And cycle 2 used 100 input tokens and 50 output tokens
    And a pod run for "JavaScript" implementing "Calculator" with 3 cycles to green
    And cycle 1 used 150 input tokens and 75 output tokens
    And cycle 2 used 150 input tokens and 75 output tokens
    And cycle 3 used 150 input tokens and 75 output tokens
    When the reporter scores the pod runs
    Then the report contains 2 language scores
    And the score for "Python" has tokens per green of 225.0
    And the score for "JavaScript" has tokens per green of 150.0
    And the comparison feature requirement is "Calculator"
    And the most efficient language is "JavaScript"
    And the efficiency ratio is 1.5

  Scenario: Score pod runs for different features produces no comparison
    Given a pod run for "Python" implementing "Login" with 2 cycles to green
    And cycle 1 used 100 input tokens and 50 output tokens
    And cycle 2 used 100 input tokens and 50 output tokens
    And a pod run for "JavaScript" implementing "Logout" with 1 cycles to green
    And cycle 1 used 200 input tokens and 100 output tokens
    When the reporter scores the pod runs
    Then the report contains 2 language scores
    And the report has no comparison

  Scenario: Score pod run with zero cycles to green produces infinite tokens per green
    Given a pod run for "Ruby" implementing "Feature X" with 0 cycles to green
    And cycle 1 used 100 input tokens and 50 output tokens
    When the reporter scores the pod runs
    Then the report contains 1 language score
    And the score for "Ruby" has tokens per green of infinity

  Scenario: Convert efficiency report to dictionary format
    Given a pod run for "Go" implementing "API endpoint" with 1 cycles to green
    And cycle 1 used 300 input tokens and 200 output tokens
    When the reporter scores the pod runs
    And the report is converted to dictionary
    Then the dictionary has key "tokenEfficiency"
    And the tokenEfficiency contains "scores" list with 1 entry
    And the first score has language "Go"
    And the first score has featureRequirement "API endpoint"
    And the first score has totalInputTokens 300
    And the first score has totalOutputTokens 200
    And the first score has cyclesToGreen 1
    And the first score has tokensPerGreen 500.0
    And the tokenEfficiency contains "comparison" with value None

  Scenario: Convert efficiency report with comparison to dictionary format
    Given a pod run for "Rust" implementing "Parser" with 4 cycles to green
    And cycle 1 used 100 input tokens and 100 output tokens
    And cycle 2 used 100 input tokens and 100 output tokens
    And cycle 3 used 100 input tokens and 100 output tokens
    And cycle 4 used 100 input tokens and 100 output tokens
    And a pod run for "C++" implementing "Parser" with 2 cycles to green
    And cycle 1 used 150 input tokens and 150 output tokens
    And cycle 2 used 150 input tokens and 150 output tokens
    When the reporter scores the pod runs
    And the report is converted to dictionary
    Then the comparison in dictionary has featureRequirement "Parser"
    And the comparison in dictionary has mostEfficient "C++"
    And the comparison in dictionary has efficiencyRatio 1.3333333333333333
    And the comparison in dictionary has scores list with 2 entries

  Scenario: Score single pod run with one cycle
    Given a pod run for "TypeScript" implementing "Validator" with 1 cycles to green
    And cycle 1 used 500 input tokens and 250 output tokens
    When the reporter scores the pod runs
    Then the report contains 1 language score
    And the score for "TypeScript" has total input tokens of 500
    And the score for "TypeScript" has total output tokens of 250
    And the score for "TypeScript" has tokens per green of 750.0