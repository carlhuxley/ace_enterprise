Feature: MLflow Knowledge Query Interface

  Scenario: Initialize query interface with experiment name
    Given MLflow is available
    When I create an MLflowKnowledgeQuery with experimentName "image_classification"
    Then the query interface is initialized successfully
    And the experiment "image_classification" exists in MLflow

  Scenario: Get enriched runs with no filter
    Given an MLflowKnowledgeQuery for experiment "sentiment_analysis"
    And the experiment has 3 MLflow runs
    And the knowledge base contains 2 decisions for run "run_001"
    When I call getEnrichedRuns with no filter and maxResults 100
    Then I receive 3 EnrichedRun objects
    And each EnrichedRun contains runId, experimentId, status, startTime, params, metrics, and tags
    And each EnrichedRun contains decisions, relatedPatterns, decisionCount, hasFailedDecisions, and appliedPatterns

  Scenario: Get enriched runs with MLflow filter string
    Given an MLflowKnowledgeQuery for experiment "model_training"
    And the experiment has 5 MLflow runs
    And 2 runs have params.learningRate greater than 0.001
    When I call getEnrichedRuns with filterString "params.learningRate > '0.001'" and maxResults 100
    Then I receive 2 EnrichedRun objects

  Scenario: Find runs by decision question and outcome
    Given an MLflowKnowledgeQuery for experiment "hyperparameter_tuning"
    And run "run_123" has a decision with question "Which optimizer to use?" and decision "Adam" and outcome "successful"
    And run "run_456" has a decision with question "Which optimizer to use?" and decision "SGD" and outcome "failed"
    And run "run_789" has a decision with question "What batch size?" and decision "32" and outcome "successful"
    When I call findRunsByDecision with question "optimizer", decision "Adam", and outcome "successful"
    Then I receive 1 EnrichedRun object
    And the runId is "run_123"

  Scenario: Find runs by pattern name
    Given an MLflowKnowledgeQuery for experiment "deep_learning"
    And the knowledge base has a pattern named "Early Stopping Pattern"
    And the pattern was observed in experiments "run_001" and "run_002"
    When I call findRunsByPattern with patternName "Early Stopping"
    Then I receive 2 EnrichedRun objects
    And the runIds are "run_001" and "run_002"

  Scenario: Get recommendations for parameters with domain tags
    Given an MLflowKnowledgeQuery for experiment "nlp_training"
    And the knowledge base has a pattern with successRate 0.85 and domainTags ["nlp", "transformers"]
    And the pattern whenToApply mentions "batchSize" and "128"
    When I call getRecommendationsForParams with params {"batchSize": 128, "optimizer": "adam"} and domainTags ["nlp"] and minSuccessRate 0.7
    Then I receive a list of tuples containing ExperimentPattern and relevanceReason
    And the first recommendation has a relevanceReason mentioning "batchSize"
    And recommendations are sorted by usefulnessScore in descending order

  Scenario: Get decision history filtered by keyword
    Given an MLflowKnowledgeQuery for experiment "model_selection"
    And the knowledge base has 5 decisions
    And 2 decisions have "learning rate" in the question
    And decisions have timestamps 1000, 2000, 3000, 4000, 5000
    When I call getDecisionHistory with questionKeyword "learning rate"
    Then I receive 2 ExperimentDecision objects
    And the decisions are sorted by timestamp in descending order

  Scenario: Compare two runs with different parameters and metrics
    Given an MLflowKnowledgeQuery for experiment "ab_testing"
    And run "run_A" has params {"learningRate": "0.001", "batchSize": "32"} and metrics {"accuracy": 0.85, "loss": 0.3}
    And run "run_B" has params {"learningRate": "0.01", "batchSize": "32"} and metrics {"accuracy": 0.90, "loss": 0.2}
    And run "run_A" has a decision with question "Use dropout?" and decision "Yes"
    And run "run_B" has a decision with question "Use dropout?" and decision "No"
    When I call compareRuns with runId1 "run_A" and runId2 "run_B"
    Then I receive a comparison dictionary
    And paramDifferences contains "learningRate" with run1 "0.001" and run2 "0.01"
    And metricDifferences contains "accuracy" with run1 0.85, run2 0.90, diff 0.05, and pctChange 5.88
    And decisionDifferences contains "Use dropout?" with run1 "Yes" and run2 "No"

  Scenario: Attempt to initialize without MLflow available
    Given MLflow is not available
    When I attempt to create an MLflowKnowledgeQuery with experimentName "test_experiment"
    Then an ImportError is raised with message "MLflow is required. Install with: pip install mlflow"