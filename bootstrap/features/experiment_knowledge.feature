Feature: ML Experiment Knowledge Management
  As a machine learning practitioner
  I want to track decisions and patterns across experiments
  So that I can build and query a knowledge base of ML experimentation insights

  Scenario: Create a new experiment knowledge base
    Given I create an MLExperimentKnowledge with experimentName "image_classification"
    When I access the experimentName attribute
    Then it should return "image_classification"
    And the decisions list should be empty
    And the patterns list should be empty

  Scenario: Add a decision to the knowledge base
    Given I create an MLExperimentKnowledge with experimentName "nlp_training"
    And I create an ExperimentDecision with decisionId "dec_001", question "Which optimizer?", decision "Adam", and rationale "Best for transformers"
    When I call addDecision with the decision
    Then the decisions list should contain 1 decision
    And the first decision should have decisionId "dec_001"

  Scenario: Add a pattern to the knowledge base
    Given I create an MLExperimentKnowledge with experimentName "cv_experiments"
    And I create an ExperimentPattern with patternId "pat_001", patternName "LR Warmup", successRate 0.85, and experimentsCount 5
    When I call addPattern with the pattern
    Then the patterns list should contain 1 pattern
    And the first pattern should have patternId "pat_001"

  Scenario: Retrieve decisions for a specific MLflow run
    Given I create an MLExperimentKnowledge with experimentName "model_tuning"
    And I create an ExperimentDecision with decisionId "dec_001" and context containing mlflowRunId "run_123"
    And I create an ExperimentDecision with decisionId "dec_002" and context containing mlflowRunId "run_456"
    And I add both decisions to the knowledge base
    When I call getDecisionsForRun with "run_123"
    Then it should return 1 decision
    And the returned decision should have decisionId "dec_001"

  Scenario: Filter patterns by domain tag
    Given I create an MLExperimentKnowledge with experimentName "multi_domain"
    And I create an ExperimentPattern with patternId "pat_001" and domainTags containing "computer_vision"
    And I create an ExperimentPattern with patternId "pat_002" and domainTags containing "nlp"
    And I create an ExperimentPattern with patternId "pat_003" and domainTags containing "computer_vision"
    And I add all patterns to the knowledge base
    When I call getPatternsByDomain with "computer_vision"
    Then it should return 2 patterns
    And the returned patterns should have patternIds "pat_001" and "pat_003"

  Scenario: Filter patterns by success rate and experiment count
    Given I create an MLExperimentKnowledge with experimentName "pattern_analysis"
    And I create an ExperimentPattern with patternId "pat_001", successRate 0.8, and experimentsCount 5
    And I create an ExperimentPattern with patternId "pat_002", successRate 0.6, and experimentsCount 3
    And I create an ExperimentPattern with patternId "pat_003", successRate 0.9, and experimentsCount 2
    And I add all patterns to the knowledge base
    When I call getSuccessfulPatterns with minSuccessRate 0.7 and minExperiments 3
    Then it should return 1 pattern
    And the returned pattern should have patternId "pat_001"

  Scenario: Save and load knowledge base to JSON file
    Given I create an MLExperimentKnowledge with experimentName "persistence_test"
    And I create an ExperimentDecision with decisionId "dec_001" and question "Test question"
    And I add the decision to the knowledge base
    And I create an ExperimentPattern with patternId "pat_001" and patternName "Test pattern"
    And I add the pattern to the knowledge base
    When I call save with filepath "test_knowledge.json"
    And I call load with filepath "test_knowledge.json"
    Then the loaded knowledge base should have experimentName "persistence_test"
    And the loaded knowledge base should contain 1 decision with decisionId "dec_001"
    And the loaded knowledge base should contain 1 pattern with patternId "pat_001"

  Scenario: Convert decision to dictionary and back
    Given I create an ExperimentDecision with decisionId "dec_001", question "Which loss?", decision "CrossEntropy", rationale "Standard for classification", and alternativesConsidered containing "FocalLoss" and "MSE"
    When I call toDict on the decision
    And I call fromDict with the resulting dictionary
    Then the reconstructed decision should have decisionId "dec_001"
    And the reconstructed decision should have question "Which loss?"
    And the reconstructed decision should have alternativesConsidered containing "FocalLoss" and "MSE"

  Scenario: Convert pattern to dictionary and back
    Given I create an ExperimentPattern with patternId "pat_001", patternName "Batch Normalization", successRate 0.75, observedInExperiments containing "exp_1" and "exp_2", and experimentsCount 2
    When I call toDict on the pattern
    And I call fromDict with the resulting dictionary
    Then the reconstructed pattern should have patternId "pat_001"
    And the reconstructed pattern should have successRate 0.75
    And the reconstructed pattern should have observedInExperiments containing "exp_1" and "exp_2"