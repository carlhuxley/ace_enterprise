Feature: PostgreSQL-backed MLflow Callback for ML Experiment Knowledge Capture

  Scenario: Initialize callback with required parameters
    Given MLflow is available
    When I create a PostgresACEMLflowCallback with experimentName "sentiment_classifier" and playbookId "ml_nlp_experiments"
    Then the callback is initialized successfully
    And the experimentName is "sentiment_classifier"
    And the playbookId is "ml_nlp_experiments"
    And the playbookVersion is "1.0.0"

  Scenario: Initialize callback with custom version and contributor
    Given MLflow is available
    When I create a PostgresACEMLflowCallback with experimentName "image_classifier", playbookId "cv_experiments", playbookVersion "2.1.0", and humanContributor "alice@example.com"
    Then the callback is initialized successfully
    And the playbookVersion is "2.1.0"
    And the humanContributor is "alice@example.com"

  Scenario: Fail to initialize when MLflow is not available
    Given MLflow is not available
    When I attempt to create a PostgresACEMLflowCallback with experimentName "test" and playbookId "test_playbook"
    Then an ImportError is raised with message containing "MLflow required"

  Scenario: Log a decision during experimentation
    Given a PostgresACEMLflowCallback initialized with experimentName "optimizer_test" and playbookId "ml_experiments"
    When I call logDecision with question "Which optimizer to use?", decision "Adam with lr=0.001", and rationale "Better convergence in pilot runs"
    Then a decision dictionary is returned
    And the decision dictionary contains question "Which optimizer to use?"
    And the decision dictionary contains decision "Adam with lr=0.001"
    And the decision dictionary contains rationale "Better convergence in pilot runs"
    And the decision dictionary contains an empty alternatives list
    And the decision dictionary contains an empty context dictionary
    And the decision dictionary contains a timestamp

  Scenario: Log a decision with alternatives and context
    Given a PostgresACEMLflowCallback initialized with experimentName "model_selection" and playbookId "ml_experiments"
    When I call logDecision with question "Which model architecture?", decision "ResNet50", rationale "Best accuracy/speed tradeoff", alternativesConsidered ["VGG16", "EfficientNet"], and context {"datasetSize": 10000, "gpuMemory": "8GB"}
    Then a decision dictionary is returned
    And the decision dictionary contains alternatives ["VGG16", "EfficientNet"]
    And the decision dictionary contains context with datasetSize 10000
    And the decision dictionary contains context with gpuMemory "8GB"

  Scenario: Log a learned pattern with minimal information
    Given a PostgresACEMLflowCallback initialized with experimentName "bert_tuning" and playbookId "nlp_playbook"
    When I call logPattern with patternName "Adam for BERT", description "Adam optimizer works well", whenToApply "Fine-tuning BERT models", and successRate 0.95
    Then a pattern dictionary is returned
    And the pattern dictionary contains patternName "Adam for BERT"
    And the pattern dictionary contains description "Adam optimizer works well"
    And the pattern dictionary contains whenToApply "Fine-tuning BERT models"
    And the pattern dictionary contains successRate 0.95
    And the pattern dictionary contains an empty implementation string
    And the pattern dictionary contains an empty antipatterns list
    And the pattern dictionary contains an empty domainTags list
    And the pattern is added to the playbook

  Scenario: Log a learned pattern with full details
    Given a PostgresACEMLflowCallback initialized with experimentName "cnn_training" and playbookId "cv_playbook"
    When I call logPattern with patternName "Batch Normalization", description "Stabilizes training", whenToApply "After conv layers", successRate 0.88, implementation "Add BatchNorm2d after each Conv2d", antipatterns ["Using with dropout", "Before activation"], and domainTags ["computer_vision", "cnn"]
    Then a pattern dictionary is returned
    And the pattern dictionary contains implementation "Add BatchNorm2d after each Conv2d"
    And the pattern dictionary contains antipatterns ["Using with dropout", "Before activation"]
    And the pattern dictionary contains domainTags ["computer_vision", "cnn"]
    And the pattern is added to the playbook with tags including "computer_vision", "cnn", "ml_experiment", and "mlflow"

  Scenario: Finalize experiment with results
    Given a PostgresACEMLflowCallback initialized with experimentName "accuracy_test" and playbookId "test_playbook"
    And I have logged 2 decisions
    And I have logged 1 pattern
    When I call finalizeExperiment with hyperparameters {"learningRate": 0.001, "batchSize": 32}, metrics {"accuracy": 0.95, "loss": 0.12}, and success True
    Then the experiment is logged to PostgreSQL
    And the experiment log contains experimentName "accuracy_test"
    And the experiment log contains 2 decisions
    And the experiment log contains 1 pattern
    And the experiment log contains hyperparameters with learningRate 0.001
    And the experiment log contains metrics with accuracy 0.95
    And the experiment log contains success True

  Scenario: Use callback as context manager
    Given a PostgresACEMLflowCallback initialized with experimentName "context_test" and playbookId "test_playbook"
    When I use the callback as a context manager
    Then the callback enters successfully
    And the callback exits successfully without auto-finalizing