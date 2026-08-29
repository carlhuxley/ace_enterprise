Feature: Unified MLflow + ACE knowledge query interface

  Background:
    Given an ACE knowledge base exists for experiment "image_classifier" with decisions and patterns
    And MLflow tracking is available with runs recorded under experiment "image_classifier"

  Scenario: Retrieving enriched runs combines MLflow data with ACE knowledge
    Given a run "run-001" exists in experiment "image_classifier" with param "batch_size" set to "128"
    And run "run-001" has an ACE decision for the question "Which optimizer to use?" with decision "Adam" and outcome "successful"
    And run "run-001" has the tag "ace.pattern.warmup_lr" set to "warmup_lr"
    When I call get_enriched_runs for experiment "image_classifier"
    Then the result includes an enriched run with run_id "run-001"
    And that run has decision_count equal to 1
    And that run has has_failed_decisions equal to false
    And that run's applied_patterns includes "warmup_lr"

  Scenario: Filtering runs by decision outcome
    Given run "run-001" has a decision for question "Which optimizer to use?" with decision "Adam" and outcome "successful"
    And run "run-002" has a decision for question "Which optimizer to use?" with decision "SGD" and outcome "failed"
    When I call find_runs_by_decision with outcome "failed"
    Then the result contains run "run-002"
    And the result does not contain run "run-001"

  Scenario: Filtering runs by decision question and decision substrings
    Given run "run-003" has a decision for question "Which learning rate schedule?" with decision "cosine annealing"
    When I call find_runs_by_decision with question "learning rate" and decision "cosine"
    Then the result contains run "run-003"

  Scenario: Finding runs where a specific pattern was observed
    Given a pattern named "gradient_clipping" is recorded as observed in run "run-004"
    When I call find_runs_by_pattern with pattern_name "gradient"
    Then the result contains a run with run_id "run-004"

  Scenario: Finding runs by a pattern name that does not exist returns no results
    When I call find_runs_by_pattern with pattern_name "nonexistent_pattern"
    Then the result is an empty list

  Scenario: Getting parameter recommendations returns patterns above the success threshold
    Given a successful pattern "large_batch_training" has success_rate 0.85 and when_to_apply text mentioning "batch_size"
    And a pattern "flaky_pattern" has success_rate 0.4
    When I call get_recommendations_for_params with params {"batch_size": 128} and min_success_rate 0.7
    Then the result includes "large_batch_training" with a relevance reason mentioning "batch_size"
    And the result does not include "flaky_pattern"

  Scenario: Getting decision history sorted newest first and filtered by keyword
    Given decisions exist for questions "Which optimizer to use?" at timestamp 100 and "Which batch size to use?" at timestamp 200
    When I call get_decision_history with question_keyword "batch size"
    Then the result contains only the decision for "Which batch size to use?"

  Scenario: Comparing two runs reports parameter, metric, and decision differences
    Given run "run-005" has param "learning_rate" set to "0.01" and metric "accuracy" set to 0.80
    And run "run-006" has param "learning_rate" set to "0.001" and metric "accuracy" set to 0.90
    When I call compare_runs with run_id_1 "run-005" and run_id_2 "run-006"
    Then the comparison's param_differences includes "learning_rate" with run1 "0.01" and run2 "0.001"
    And the comparison's metric_differences includes "accuracy" with a diff of 0.10

  Scenario: Comparing runs where one run does not exist raises an error
    Given only run "run-007" exists in experiment "image_classifier"
    When I call compare_runs with run_id_1 "run-007" and run_id_2 "run-missing"
    Then a ValueError is raised indicating the run was not found