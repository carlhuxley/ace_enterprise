Feature: Cost-Quality Trade-off Analysis for OpenRouter
  As a system administrator
  I want to analyze the cost-quality trade-off of different OpenRouter models
  So that I can optimize for best quality per dollar spent

  Background:
    Given the cost-quality analyzer is initialized
    And models have recorded cost and quality data

  Scenario: Calculate cost per quality point for a model
    Given model "qwen/qwen3-coder:free" has the following performance:
      | total_cost_usd | total_quality_points | task_count |
      | 0.05           | 425                  | 5          |
    When I calculate cost efficiency metrics
    Then cost_per_quality_point should be 0.000118
    And quality_per_dollar should be 8500.0
    And avg_quality_score should be 85.0

  Scenario: Compare cost efficiency across models
    Given the following model performance data:
      | model_id                  | total_cost | avg_quality | task_count |
      | qwen/qwen3-coder:free     | 0.001      | 85.0        | 10         |
      | meta-llama/llama-3-8b     | 0.05       | 82.0        | 10         |
      | anthropic/claude-3-haiku  | 0.25       | 92.0        | 10         |
      | openai/gpt-4o             | 1.50       | 95.0        | 10         |
    When I rank models by quality_per_dollar
    Then the ranking should be:
      | rank | model_id                  |
      | 1    | qwen/qwen3-coder:free     |
      | 2    | meta-llama/llama-3-8b     |
      | 3    | anthropic/claude-3-haiku  |
      | 4    | openai/gpt-4o             |

  Scenario: Identify Pareto-optimal models
    Given the following model performance data:
      | model_id    | avg_quality | avg_cost_per_task |
      | model-a     | 90.0        | 0.10              |
      | model-b     | 85.0        | 0.05              |
      | model-c     | 80.0        | 0.08              |
      | model-d     | 95.0        | 0.50              |
    When I compute the Pareto frontier
    Then the Pareto-optimal models should be:
      | model_id |
      | model-a  |
      | model-b  |
      | model-d  |
    And model-c should NOT be Pareto-optimal
    Because model-b has better quality at lower cost

  Scenario: Query most cost-efficient model for a complexity level
    Given models have performance data at different complexity levels:
      | model_id    | complexity | success_rate | avg_cost |
      | model-cheap | 3          | 0.70         | 0.01     |
      | model-mid   | 3          | 0.85         | 0.10     |
      | model-prem  | 3          | 0.95         | 0.50     |
    When I query the most cost-efficient model for complexity 3
    Then the result should consider both success rate and cost
    And return the model with best value score

  Scenario: Apply budget constraint to model selection
    Given a budget constraint of 0.10 USD per task
    And the following models are available:
      | model_id    | avg_cost_per_task | avg_quality |
      | cheap-model | 0.05              | 75.0        |
      | mid-model   | 0.08              | 82.0        |
      | prem-model  | 0.25              | 95.0        |
    When I request the best model within budget
    Then prem-model should be excluded due to budget
    And mid-model should be selected as best within budget

  Scenario: Calculate acceptable quality delta for cost savings
    Given model-expensive costs 0.50 USD with quality 95
    And model-cheap costs 0.05 USD with quality 90
    When I calculate the quality delta percentage
    Then the delta should be 5.26%
    And if acceptable_delta is 10% then model-cheap is acceptable
    And if acceptable_delta is 3% then model-cheap is NOT acceptable

  Scenario: Generate cost-quality summary report
    Given multiple models with varied cost and quality profiles
    When I generate a cost-quality summary
    Then the report should include:
      | metric                    |
      | total_models_analyzed     |
      | pareto_optimal_count      |
      | best_quality_model        |
      | best_value_model          |
      | cheapest_acceptable_model |
    And each model entry should have cost_efficiency_score
