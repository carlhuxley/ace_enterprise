Feature: PostgreSQL-backed MLflow knowledge capture callback

  Scenario: Initializing the callback with no MLflow run active
    Given no MLflow run is currently active
    When I create a PostgresACEMLflowCallback with experiment_name "sentiment_classifier" and playbook_id "ml_nlp_experiments"
    Then the callback is created without error
    And no decisions or patterns have been logged yet

  Scenario: Logging a decision with minimal required information
    Given a PostgresACEMLflowCallback for experiment "sentiment_classifier" and playbook "ml_nlp_experiments"
    When I call log_decision with question "Which optimizer to use?", decision "Adam with lr=0.001", and rationale "Better convergence in pilot runs"
    Then the returned decision dictionary contains question "Which optimizer to use?", decision "Adam with lr=0.001", and rationale "Better convergence in pilot runs"
    And the returned decision dictionary has an empty "alternatives" list
    And the returned decision dictionary has an empty "context" dictionary
    And the returned decision dictionary includes a "timestamp" value

  Scenario: Logging a decision with alternatives and context
    Given a PostgresACEMLflowCallback for experiment "sentiment_classifier" and playbook "ml_nlp_experiments"
    When I call log_decision with question "Which optimizer to use?", decision "Adam with lr=0.001", rationale "Better convergence", alternatives_considered ["SGD", "RMSprop"], and context {"dataset_size": 5000}
    Then the returned decision dictionary has "alternatives" equal to ["SGD", "RMSprop"]
    And the returned decision dictionary has "context" equal to {"dataset_size": 5000}

  Scenario: Logging a learned pattern with full details
    Given a PostgresACEMLflowCallback for experiment "sentiment_classifier" and playbook "ml_nlp_experiments"
    When I call log_pattern with pattern_name "Adam works well for BERT fine-tuning", description "Adam optimizer with lr=1e-5 gives best results", when_to_apply "When fine-tuning BERT models on text classification", and success_rate 0.95
    Then the returned pattern dictionary contains pattern_name "Adam works well for BERT fine-tuning"
    And the returned pattern dictionary has "success_rate" equal to 0.95
    And the returned pattern dictionary has an empty "implementation" string
    And the returned pattern dictionary has an empty "antipatterns" list
    And the returned pattern dictionary has an empty "domain_tags" list

  Scenario: Logging a pattern with antipatterns and domain tags
    Given a PostgresACEMLflowCallback for experiment "sentiment_classifier" and playbook "ml_nlp_experiments"
    When I call log_pattern with pattern_name "Batch size tuning", description "Larger batches speed up training", when_to_apply "When GPU memory allows", success_rate 0.8, antipatterns ["Do not exceed GPU memory"], and domain_tags ["nlp"]
    Then the returned pattern dictionary has "antipatterns" equal to ["Do not exceed GPU memory"]
    And the returned pattern dictionary has "domain_tags" equal to ["nlp"]

  Scenario: Accumulating multiple decisions and patterns before finalizing
    Given a PostgresACEMLflowCallback for experiment "sentiment_classifier" and playbook "ml_nlp_experiments"
    When I call log_decision twice with different questions
    And I call log_pattern once with pattern_name "Adam works well for BERT fine-tuning"
    Then two decisions and one pattern have been recorded by the callback

  Scenario: Finalizing an experiment stores hyperparameters and metrics
    Given a PostgresACEMLflowCallback for experiment "sentiment_classifier" and playbook "ml_nlp_experiments"
    And I have logged one decision and one pattern
    When I call finalize_experiment with hyperparameters {"lr": 0.001, "batch_size": 32}, metrics {"accuracy": 0.95}, and success True
    Then the experiment is finalized without error

  Scenario: Using the callback as a context manager
    Given no MLflow run is currently active
    When I use PostgresACEMLflowCallback for experiment "sentiment_classifier" and playbook "ml_nlp_experiments" in a "with" statement
    Then the context manager yields the callback instance itself
    And exiting the "with" block does not automatically finalize the experiment