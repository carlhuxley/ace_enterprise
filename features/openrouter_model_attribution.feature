Feature: OpenRouter Model Attribution in Performance Metrics
  As a system administrator
  I want to track which OpenRouter model was actually used for each task
  So that I can analyze which models perform best for different task types

  Background:
    Given the performance aggregator is initialized
    And the audit store is available

  Scenario: Record model attribution in CYCLE_COMPLETED audit event
    Given an agent completes a task using OpenRouter
    And the LLM response includes actual_model "qwen/qwen3-coder:free"
    And the LLM response includes requested_model "qwen/qwen3-coder:free"
    When the CYCLE_COMPLETED event is recorded
    Then the audit payload should contain model_id "qwen/qwen3-coder:free"
    And the audit payload should contain requested_model "qwen/qwen3-coder:free"
    And the audit payload should contain provider "openrouter"

  Scenario: Aggregate performance metrics by model ID
    Given the following task completions are recorded:
      | model_id                  | task_type | success | quality_score |
      | qwen/qwen3-coder:free     | coding    | true    | 85            |
      | qwen/qwen3-coder:free     | coding    | true    | 90            |
      | meta-llama/llama-3-8b     | coding    | true    | 75            |
      | meta-llama/llama-3-8b     | coding    | false   | 40            |
    When I query model performance metrics
    Then model "qwen/qwen3-coder:free" should have success_rate 1.0
    And model "qwen/qwen3-coder:free" should have avg_quality_score 87.5
    And model "meta-llama/llama-3-8b" should have success_rate 0.5
    And model "meta-llama/llama-3-8b" should have avg_quality_score 57.5

  Scenario: Query top models by success rate
    Given multiple models have recorded performance data
    When I request the top 3 models by success rate
    Then I should receive a ranked list of models
    And each entry should include model_id, success_rate, and task_count

  Scenario: Filter performance by model family
    Given performance data exists for models:
      | model_id                      |
      | qwen/qwen3-coder:free         |
      | qwen/qwen-2.5-72b             |
      | meta-llama/llama-3-8b         |
      | meta-llama/llama-3.1-70b      |
    When I filter by model family "qwen"
    Then I should only see models starting with "qwen/"
    And I should see aggregated stats for the qwen family

  Scenario: Get best model for a specific task type
    Given models have varying success rates for different task types:
      | model_id                  | task_type | success_rate |
      | qwen/qwen3-coder:free     | coding    | 0.95         |
      | qwen/qwen3-coder:free     | testing   | 0.80         |
      | meta-llama/llama-3-8b     | coding    | 0.70         |
      | meta-llama/llama-3-8b     | testing   | 0.90         |
    When I query the best model for task_type "coding"
    Then the result should be "qwen/qwen3-coder:free"
    When I query the best model for task_type "testing"
    Then the result should be "meta-llama/llama-3-8b"

  Scenario: Track model performance over time
    Given model "qwen/qwen3-coder:free" has historical performance data
    When I query performance for the last 7 days
    Then I should see daily success rates
    And I should see daily average quality scores
    And I should be able to detect performance trends
