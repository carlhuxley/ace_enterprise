Feature: ML Experiment Knowledge Base

  Scenario: Recording a decision made during an experiment
    Given a knowledge base for experiment "image-classifier-v2"
    When a decision is added with question "Which optimizer to use?", decision "Adam with lr=0.001", and rationale "AdamW showed instability in early experiments"
    Then the knowledge base contains 1 decision
    And that decision has decision "Adam with lr=0.001"

  Scenario: Retrieving decisions associated with a specific MLflow run
    Given a knowledge base for experiment "image-classifier-v2"
    And a decision with context {"mlflow_run_id": "run-123"} has been added
    And a decision with context {"mlflow_run_id": "run-456"} has been added
    When decisions for MLflow run "run-123" are requested
    Then 1 decision is returned
    And its context contains "mlflow_run_id" equal to "run-123"

  Scenario: Recording a learned pattern
    Given a knowledge base for experiment "image-classifier-v2"
    When a pattern is added with name "Learning rate warmup for large batches", success rate 0.85, and domain tags ["vision", "batch-training"]
    Then the knowledge base contains 1 pattern

  Scenario: Filtering patterns by domain tag
    Given a knowledge base with a pattern tagged with domain "vision"
    And a knowledge base with a pattern tagged with domain "nlp"
    When patterns for domain "vision" are requested
    Then only the pattern tagged "vision" is returned

  Scenario: Filtering patterns by minimum success rate and experiment count
    Given a pattern with success rate 0.9 and experiments count 5
    And a pattern with success rate 0.4 and experiments count 5
    When successful patterns are requested with min_success_rate 0.7 and min_experiments 1
    Then only the pattern with success rate 0.9 is returned

  Scenario: Saving and loading a knowledge base preserves its contents
    Given a knowledge base for experiment "image-classifier-v2" containing 1 decision and 1 pattern
    When the knowledge base is saved to file "knowledge.json"
    And a new knowledge base is loaded from file "knowledge.json"
    Then the loaded knowledge base has experiment name "image-classifier-v2"
    And the loaded knowledge base contains 1 decision and 1 pattern

  Scenario: Adding a decision updates the knowledge base's last-updated timestamp
    Given a knowledge base for experiment "image-classifier-v2" with a known updated_at timestamp
    When a new decision is added
    Then the knowledge base's updated_at timestamp is more recent than before

  Scenario: A newly created knowledge base has no decisions or patterns
    Given a new knowledge base is created for experiment "text-summarizer"
    Then the knowledge base contains 0 decisions
    And the knowledge base contains 0 patterns