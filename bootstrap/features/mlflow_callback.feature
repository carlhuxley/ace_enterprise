Feature: ACE MLflow Callback for Experiment Knowledge Capture

  Scenario: Initialize callback with default knowledge directory
    Given MLflow is available
    When I create an ACEMLflowCallback with experimentName "my_experiment"
    Then a new knowledge base is created for "my_experiment"
    And the knowledge directory is set to "~/.ace/ml_experiments"
    And autoSave is enabled by default

  Scenario: Initialize callback with existing knowledge file
    Given MLflow is available
    And a knowledge file exists at "~/.ace/ml_experiments/existing_experiment.json"
    When I create an ACEMLflowCallback with experimentName "existing_experiment"
    Then the existing knowledge base is loaded from the file

  Scenario: Log a decision during an experiment
    Given MLflow is available
    And I have an ACEMLflowCallback with experimentName "optimizer_test"
    When I call logDecision with question "Which optimizer to use?", decision "Adam with lr=0.001", and rationale "Better convergence in pilot runs"
    Then an ExperimentDecision object is returned
    And the decision has a decisionId starting with "dec_optimizer_test_"
    And the decision contains question "Which optimizer to use?"
    And the decision contains decision "Adam with lr=0.001"
    And the decision contains rationale "Better convergence in pilot runs"
    And the decision is added to the knowledge base
    And the knowledge is automatically saved to disk

  Scenario: Log a decision with alternatives and context
    Given MLflow is available
    And I have an ACEMLflowCallback with experimentName "model_selection"
    And there is an active MLflow run with runId "run_12345"
    When I call logDecision with question "Which model architecture?", decision "ResNet50", rationale "Best accuracy/speed tradeoff", alternativesConsidered ["VGG16", "EfficientNet"], and context {"previousAccuracy": 0.85}
    Then an ExperimentDecision object is returned
    And the decision contains alternativesConsidered ["VGG16", "EfficientNet"]
    And the decision context includes "mlflow_run_id" with value "run_12345"
    And the decision context includes "previous_accuracy" with value 0.85

  Scenario: Log a learned pattern from multiple experiments
    Given MLflow is available
    And I have an ACEMLflowCallback with experimentName "training_patterns"
    When I call logPattern with patternName "Early Stopping at Plateau", description "Stop training when validation loss plateaus", whenToApply "When validation loss stops improving", implementation "Use EarlyStopping callback with patience=5", observedInRuns ["run_1", "run_2", "run_3"], and successRate 0.85
    Then an ExperimentPattern object is returned
    And the pattern has a patternId starting with "pat_training_patterns_"
    And the pattern has patternName "Early Stopping at Plateau"
    And the pattern has successRate 0.85
    And the pattern has experimentsCount 3
    And the pattern has timesApplied 3
    And the pattern has timesSuccessful 2
    And the pattern is added to the knowledge base

  Scenario: Update decision outcome after experiment completion
    Given MLflow is available
    And I have an ACEMLflowCallback with experimentName "hyperparameter_tuning"
    And I have logged a decision with decisionId "dec_hyperparameter_tuning_20240115_143022_1"
    When I call updateDecisionOutcome with decisionId "dec_hyperparameter_tuning_20240115_143022_1", outcome "successful", and learnedInsight "Achieved 95% accuracy"
    Then the decision outcome is updated to "successful"
    And the decision learnedInsight is set to "Achieved 95% accuracy"
    And the knowledge is automatically saved to disk

  Scenario: Get pattern recommendations filtered by domain
    Given MLflow is available
    And I have an ACEMLflowCallback with experimentName "cv_experiments"
    And the knowledge base contains patterns with domainTags ["computer_vision"] and successRate 0.8
    And the knowledge base contains patterns with domainTags ["nlp"] and successRate 0.9
    When I call getRecommendations with currentParams {"batchSize": 32} and domainTags ["computer_vision"]
    Then only patterns with domainTags containing "computer_vision" are returned
    And patterns with successRate below 0.7 are excluded
    And the patterns are sorted by usefulnessScore in descending order

  Scenario: Use callback as context manager with auto-save
    Given MLflow is available
    And I have an ACEMLflowCallback with experimentName "context_test" and autoSave True
    When I enter the context manager
    And I log a decision with question "Test question", decision "Test decision", and rationale "Test rationale"
    And I exit the context manager
    Then the knowledge is saved to disk on exit

  Scenario: Raise error when MLflow is not available
    Given MLflow is not available
    When I attempt to create an ACEMLflowCallback with experimentName "test"
    Then an ImportError is raised with message "MLflow is required. Install with: pip install mlflow"