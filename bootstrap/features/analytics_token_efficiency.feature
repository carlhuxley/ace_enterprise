Feature: Token Efficiency Reporting
  As a caller of TokenEfficiencyReporter
  I want to compute per-language token efficiency scores from pod run data
  So that I can identify which language implementation is most token-efficient for a feature

  Scenario: Scoring a single pod run computes total tokens and tokens per green cycle
    Given a pod run for language "python" on feature requirement "parse_csv" with cycles_to_green 4
    And that pod run has token usage of 100 input tokens and 50 output tokens for cycle 1
    And that pod run has token usage of 80 input tokens and 40 output tokens for cycle 2
    When I score the pod run with TokenEfficiencyReporter
    Then the resulting language score for "python" has total_input_tokens 180
    And the resulting language score for "python" has total_output_tokens 90
    And the resulting language score for "python" has tokens_per_green 67.5
    And the report's comparison is None

  Scenario: A pod run with zero cycles to green yields infinite tokens per green
    Given a pod run for language "rust" on feature requirement "parse_csv" with cycles_to_green 0
    And that pod run has token usage of 200 input tokens and 100 output tokens for cycle 1
    When I score the pod run with TokenEfficiencyReporter
    Then the resulting language score for "rust" has tokens_per_green equal to infinity

  Scenario: Scoring multiple languages for the same feature produces a cross-language comparison
    Given a pod run for language "python" on feature requirement "parse_csv" with cycles_to_green 4 and total tokens 300
    And a pod run for language "go" on feature requirement "parse_csv" with cycles_to_green 2 and total tokens 100
    When I score both pod runs together with TokenEfficiencyReporter
    Then the report contains a comparison for feature requirement "parse_csv"
    And the comparison identifies "go" as the most efficient language
    And the comparison's efficiency_ratio is 1.5

  Scenario: Pod runs for different feature requirements produce no comparison
    Given a pod run for language "python" on feature requirement "parse_csv" with cycles_to_green 4
    And a pod run for language "go" on feature requirement "sort_list" with cycles_to_green 2
    When I score both pod runs together with TokenEfficiencyReporter
    Then the report's comparison is None
    And the report contains two language scores

  Scenario: Scoring an empty list of pod runs produces an empty report
    Given no pod runs
    When I score the empty list with TokenEfficiencyReporter
    Then the report contains zero language scores
    And the report's comparison is None

  Scenario: A pod run with no token usage entries scores zero total tokens
    Given a pod run for language "java" on feature requirement "parse_csv" with cycles_to_green 3
    And that pod run has no token usage entries
    When I score the pod run with TokenEfficiencyReporter
    Then the resulting language score for "java" has total_input_tokens 0
    And the resulting language score for "java" has total_output_tokens 0
    And the resulting language score for "java" has tokens_per_green 0.0

  Scenario: The efficiency report serializes to a dictionary under the token_efficiency key
    Given a pod run for language "python" on feature requirement "parse_csv" with cycles_to_green 4 and total tokens 300
    And a pod run for language "go" on feature requirement "parse_csv" with cycles_to_green 2 and total tokens 100
    When I score both pod runs together with TokenEfficiencyReporter
    And I convert the report to a dictionary
    Then the dictionary has a top-level key "token_efficiency"
    And the "token_efficiency" value contains a "scores" list with 2 entries
    And the "token_efficiency" value contains a "comparison" entry with most_efficient "go"

  Scenario: Comparing three languages for the same feature includes all in the comparison group
    Given a pod run for language "python" on feature requirement "sort_list" with cycles_to_green 5 and total tokens 500
    And a pod run for language "go" on feature requirement "sort_list" with cycles_to_green 5 and total tokens 200
    And a pod run for language "rust" on feature requirement "sort_list" with cycles_to_green 5 and total tokens 150
    When I score all three pod runs together with TokenEfficiencyReporter
    Then the comparison's scores list contains 3 entries
    And the comparison identifies "rust" as the most efficient language