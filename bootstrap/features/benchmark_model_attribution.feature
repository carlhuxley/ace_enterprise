Feature: OpenRouter Model Attribution Tracking
  As a caller of the ModelAttributionTracker
  I want to record task completions with model attribution
  And query aggregated performance metrics
  So that I can understand which models perform best

  Scenario: Recording a task completion returns the recorded data
    Given a new model attribution tracker
    When I record a completion for model "qwen/qwen-2.5-72b" requested as "qwen/qwen-2.5-72b" via provider "openrouter" for task type "coding" with success True and quality score 85.0
    Then the returned completion has model_id "qwen/qwen-2.5-72b"
    And the returned completion has task_type "coding"
    And the returned completion has success True
    And the returned completion has quality_score 85.0

  Scenario: Aggregated metrics accumulate across multiple completions for the same model
    Given a new model attribution tracker
    When I record a completion for model "openai/gpt-4o" for task type "coding" with success True and quality score 90.0
    And I record a completion for model "openai/gpt-4o" for task type "testing" with success False and quality score 40.0
    Then the metrics for model "openai/gpt-4o" report a task_count of 2
    And the metrics for model "openai/gpt-4o" report a success_rate of 0.5
    And the metrics for model "openai/gpt-4o" report an avg_quality_score of 65.0

  Scenario: Querying metrics for a model with no recorded completions returns nothing
    Given a new model attribution tracker
    When I request metrics for model "unknown/model"
    Then the result is None

  Scenario: Top models are ranked by success rate by default
    Given a new model attribution tracker
    When I record a completion for model "model-a" with success True and quality score 80.0
    And I record a completion for model "model-b" with success False and quality score 95.0
    And I record a completion for model "model-b" with success False and quality score 95.0
    Then requesting the top 2 models returns "model-a" ranked above "model-b"

  Scenario: Models below the minimum task count are excluded from top model rankings
    Given a new model attribution tracker
    When I record a single completion for model "rare-model" with success True and quality score 100.0
    Then requesting top models with a minimum task count of 2 does not include "rare-model"

  Scenario: Filtering by model family returns only models with matching prefix
    Given a new model attribution tracker
    When I record a completion for model "qwen/qwen-2.5-72b"
    And I record a completion for model "qwen/qwen-2-7b"
    And I record a completion for model "openai/gpt-4o"
    Then filtering by family "qwen" returns metrics for exactly the models "qwen/qwen-2.5-72b" and "qwen/qwen-2-7b"

  Scenario: Aggregated family metrics sum task counts across all matching models
    Given a new model attribution tracker
    When I record a completion for model "qwen/qwen-2.5-72b" with success True and quality score 80.0
    And I record a completion for model "qwen/qwen-2-7b" with success True and quality score 60.0
    Then the family metrics for "qwen" report a task_count of 2
    And the family metrics for "qwen" report a models list containing "qwen/qwen-2.5-72b" and "qwen/qwen-2-7b"

  Scenario: The best model for a task type is the one with the highest success rate meeting the minimum task count
    Given a new model attribution tracker
    When I record a completion for model "model-x" for task type "review" with success True and quality score 70.0
    And I record a completion for model "model-y" for task type "review" with success False and quality score 70.0
    Then the best model for task type "review" is "model-x"

  Scenario: Building an audit payload returns the attribution fields as a dict
    Given a new model attribution tracker
    When I create an audit payload for model_id "qwen/qwen-2.5-72b", requested_model "qwen/qwen-2.5-72b", provider "openrouter"
    Then the payload equals a dict with model_id "qwen/qwen-2.5-72b", requested_model "qwen/qwen-2.5-72b", and provider "openrouter"