Feature: Cost Quality Analyzer

  Scenario: Calculating cost efficiency metrics from per-prediction data
    Given performance data with model_name "gpt-4", accuracy 0.9, and cost_per_prediction 0.002
    When cost efficiency metrics are calculated
    Then the cost_per_quality_point is 0.002222
    And the quality_per_dollar is 450.0
    And the avg_quality_score is 0.9
    And the efficiency_grade is "C"

  Scenario: Calculating cost efficiency metrics from total metrics data
    Given performance data with total_cost_usd 10.0, total_quality_points 60000, and task_count 100
    When cost efficiency metrics are calculated
    Then the cost_per_quality_point is 0.000167
    And the quality_per_dollar is 6000.0
    And the avg_quality_score is 600.0
    And the efficiency_grade is "A"

  Scenario: Efficiency metrics include metadata with a timestamp and input hash
    Given performance data with model_name "claude-3", accuracy 0.85, and cost_per_prediction 0.005
    When cost efficiency metrics are calculated
    Then the result includes a metadata field with a calculated_at timestamp
    And the result includes a metadata field with an input_hash value

  Scenario: Ranking models by quality per dollar
    Given a list of models:
      | model_name | accuracy | cost_per_prediction |
      | model-a    | 0.8      | 0.01                 |
      | model-b    | 0.9      | 0.002                |
      | model-c    | 0.7      | 0.005                |
    When models are ranked by quality per dollar
    Then the ranked order is "model-b", "model-c", "model-a"

  Scenario: Computing the Pareto frontier excludes dominated models
    Given a list of models:
      | model_name | accuracy | cost_per_prediction |
      | model-x    | 0.9      | 0.01                 |
      | model-y    | 0.95     | 0.005                |
      | model-z    | 0.6      | 0.02                 |
    When the Pareto frontier is computed
    Then the frontier contains "model-y" but not "model-x" or "model-z"

  Scenario: Calculating quality delta percentage between two models
    Given a higher quality model with accuracy 0.95
    And a lower quality model with accuracy 0.80
    When the quality delta percentage is calculated
    Then the result is approximately 18.75

  Scenario: Querying the best model for a complexity level with qualifying models
    Given a list of models with complexity "high":
      | model_name | success_rate | value_score |
      | model-p    | 0.92         | 50           |
      | model-q    | 0.95         | 80           |
      | model-r    | 0.85         | 100          |
    When the best model for complexity "high" is queried
    Then the returned model is "model-q"

  Scenario: Querying the best model raises an error when no models match the complexity level
    Given a list of models with complexity "medium" only
    When the best model for complexity "high" is queried
    Then a ValueError is raised indicating no models were found for that complexity level