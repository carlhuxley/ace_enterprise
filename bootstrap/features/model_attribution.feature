Feature: Model Attribution Tracker

  Scenario: Recording a task completion with model attribution
    Given a new ModelAttributionTracker
    When I record a completion with modelId "qwen/qwen-2.5-coder-32b", requestedModel "qwen/qwen-2.5-coder-32b", provider "openrouter", taskType "coding", success True, and qualityScore 85.5
    Then the returned TaskCompletion has modelId "qwen/qwen-2.5-coder-32b"
    And the returned TaskCompletion has success True
    And the returned TaskCompletion has qualityScore 85.5

  Scenario: Retrieving aggregated metrics for a specific model
    Given a new ModelAttributionTracker
    And I record a completion with modelId "gpt-4", requestedModel "gpt-4", provider "openrouter", taskType "coding", success True, and qualityScore 90.0
    And I record a completion with modelId "gpt-4", requestedModel "gpt-4", provider "openrouter", taskType "testing", success False, and qualityScore 60.0
    When I get model metrics for "gpt-4"
    Then the ModelMetrics has taskCount 2
    And the ModelMetrics has successCount 1
    And the ModelMetrics has successRate 0.5
    And the ModelMetrics has avgQualityScore 75.0

  Scenario: Getting top models ranked by success rate
    Given a new ModelAttributionTracker
    And I record a completion with modelId "model-a", requestedModel "model-a", provider "openrouter", taskType "coding", success True, and qualityScore 80.0
    And I record a completion with modelId "model-a", requestedModel "model-a", provider "openrouter", taskType "coding", success True, and qualityScore 90.0
    And I record a completion with modelId "model-b", requestedModel "model-b", provider "openrouter", taskType "coding", success True, and qualityScore 70.0
    And I record a completion with modelId "model-b", requestedModel "model-b", provider "openrouter", taskType "coding", success False, and qualityScore 50.0
    And I record a completion with modelId "model-c", requestedModel "model-c", provider "openrouter", taskType "coding", success False, and qualityScore 40.0
    When I get top 2 models sorted by "success_rate" with minTaskCount 1
    Then the result contains 2 models
    And the first model has modelId "model-a" with successRate 1.0
    And the second model has modelId "model-b" with successRate 0.5

  Scenario: Filtering models by family prefix
    Given a new ModelAttributionTracker
    And I record a completion with modelId "qwen/qwen-2.5-coder-32b", requestedModel "qwen/qwen-2.5-coder-32b", provider "openrouter", taskType "coding", success True, and qualityScore 85.0
    And I record a completion with modelId "qwen/qwen-2-72b", requestedModel "qwen/qwen-2-72b", provider "openrouter", taskType "coding", success True, and qualityScore 80.0
    And I record a completion with modelId "gpt-4", requestedModel "gpt-4", provider "openrouter", taskType "coding", success True, and qualityScore 90.0
    When I filter by model family "qwen"
    Then the result contains 2 models
    And all models have modelId starting with "qwen/"

  Scenario: Getting aggregated metrics for a model family
    Given a new ModelAttributionTracker
    And I record a completion with modelId "qwen/qwen-2.5-coder-32b", requestedModel "qwen/qwen-2.5-coder-32b", provider "openrouter", taskType "coding", success True, and qualityScore 85.0
    And I record a completion with modelId "qwen/qwen-2-72b", requestedModel "qwen/qwen-2-72b", provider "openrouter", taskType "coding", success False, and qualityScore 70.0
    And I record a completion with modelId "qwen/qwen-2.5-coder-32b", requestedModel "qwen/qwen-2.5-coder-32b", provider "openrouter", taskType "testing", success True, and qualityScore 90.0
    When I get family metrics for "qwen"
    Then the ModelFamilyMetrics has family "qwen"
    And the ModelFamilyMetrics has taskCount 3
    And the ModelFamilyMetrics has successCount 2
    And the ModelFamilyMetrics has successRate 0.6666666666666666
    And the ModelFamilyMetrics has avgQualityScore 81.66666666666667

  Scenario: Finding the best model for a specific task type
    Given a new ModelAttributionTracker
    And I record a completion with modelId "model-a", requestedModel "model-a", provider "openrouter", taskType "coding", success True, and qualityScore 90.0
    And I record a completion with modelId "model-a", requestedModel "model-a", provider "openrouter", taskType "coding", success True, and qualityScore 85.0
    And I record a completion with modelId "model-b", requestedModel "model-b", provider "openrouter", taskType "coding", success True, and qualityScore 80.0
    And I record a completion with modelId "model-b", requestedModel "model-b", provider "openrouter", taskType "coding", success False, and qualityScore 60.0
    And I record a completion with modelId "model-a", requestedModel "model-a", provider "openrouter", taskType "testing", success False, and qualityScore 50.0
    When I get the best model for task type "coding" with minTaskCount 2
    Then the result is "model-a"

  Scenario: Getting daily metrics for a model over a period
    Given a new ModelAttributionTracker
    And I record a completion with modelId "model-x", requestedModel "model-x", provider "openrouter", taskType "coding", success True, qualityScore 80.0, and timestamp "2024-01-15 10:00:00"
    And I record a completion with modelId "model-x", requestedModel "model-x", provider "openrouter", taskType "coding", success False, qualityScore 60.0, and timestamp "2024-01-15 14:00:00"
    And I record a completion with modelId "model-x", requestedModel "model-x", provider "openrouter", taskType "coding", success True, qualityScore 90.0, and timestamp "2024-01-16 10:00:00"
    When I get daily metrics for "model-x" over 7 days ending "2024-01-17 23:59:59"
    Then the result contains 2 daily metrics
    And the first DailyMetrics has date "2024-01-15", taskCount 2, successCount 1, and avgQualityScore 70.0
    And the second DailyMetrics has date "2024-01-16", taskCount 1, successCount 1, and avgQualityScore 90.0

  Scenario: Detecting performance trend for a model
    Given a new ModelAttributionTracker
    And I record a completion with modelId "model-y", requestedModel "model-y", provider "openrouter", taskType "coding", success False, qualityScore 50.0, and timestamp "2024-01-10 10:00:00"
    And I record a completion with modelId "model-y", requestedModel "model-y", provider "openrouter", taskType "coding", success False, qualityScore 55.0, and timestamp "2024-01-11 10:00:00"
    And I record a completion with modelId "model-y", requestedModel "model-y", provider "openrouter", taskType "coding", success True, qualityScore 85.0, and timestamp "2024-01-12 10:00:00"
    And I record a completion with modelId "model-y", requestedModel "model-y", provider "openrouter", taskType "coding", success True, qualityScore 90.0, and timestamp "2024-01-13 10:00:00"
    When I detect performance trend for "model-y" over 7 days
    Then the trend is "improving"

  Scenario: Creating an audit payload with model attribution
    Given a new ModelAttributionTracker
    When I create an audit payload with modelId "gpt-4-turbo", requestedModel "gpt-4", and provider "openrouter"
    Then the payload contains key "modelId" with value "gpt-4-turbo"
    And the payload contains key "requestedModel" with value "gpt-4"
    And the payload contains key "provider" with value "openrouter"