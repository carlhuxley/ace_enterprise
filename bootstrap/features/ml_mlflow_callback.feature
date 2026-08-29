Feature: ACE MLflow Callback for experiment knowledge capture

  Scenario: Initializing a callback creates a new knowledge base when none exists
    Given no knowledge file exists for experiment "vision_experiment"
    When an ACEMLflowCallback is created with experiment_name "vision_experiment"
    Then a new empty knowledge base is created for "vision_experiment"

  Scenario: Initializing a callback loads an existing knowledge base
    Given a knowledge file already exists for experiment "vision_experiment" containing one decision
    When an ACEMLflowCallback is created with experiment_name "vision_experiment"
    Then the existing decision is available in the loaded knowledge base

  Scenario: Logging a decision returns a populated decision object
    Given an ACEMLflowCallback for experiment "vision_experiment" with auto_save enabled
    When log_decision is called with question "Which optimizer to use?", decision "Adam with lr=0.001", rationale "Better convergence in pilot runs", and alternatives_considered ["SGD", "AdamW"]
    Then the returned decision has question "Which optimizer to use?"
    And the returned decision has decision "Adam with lr=0.001"
    And the returned decision has alternatives_considered ["SGD", "AdamW"]
    And the decision is persisted to the knowledge file on disk

  Scenario: Logging a pattern computes derived success statistics
    Given an ACEMLflowCallback for experiment "vision_experiment"
    When log_pattern is called with pattern_name "batch_norm_before_activation", observed_in_runs ["run_1", "run_2", "run_3", "run_4"], and success_rate 0.75
    Then the returned pattern has experiments_count 4
    And the returned pattern has times_applied 4
    And the returned pattern has times_successful 3

  Scenario: Updating the outcome of an existing decision
    Given an ACEMLflowCallback for experiment "vision_experiment" with a previously logged decision "dec_vision_experiment_20260101_120000_1"
    When update_decision_outcome is called with decision_id "dec_vision_experiment_20260101_120000_1", outcome "successful", and learned_insight "Adam converged 2x faster"
    Then the decision "dec_vision_experiment_20260101_120000_1" has outcome "successful"
    And the decision "dec_vision_experiment_20260101_120000_1" has learned_insight "Adam converged 2x faster"

  Scenario: Updating the outcome of a decision that does not exist has no effect
    Given an ACEMLflowCallback for experiment "vision_experiment" with no decisions logged
    When update_decision_outcome is called with decision_id "nonexistent_id" and outcome "failed"
    Then no error is raised
    And the knowledge base remains unchanged

  Scenario: Getting recommendations filters patterns by minimum success rate
    Given an ACEMLflowCallback for experiment "vision_experiment" with a pattern "high_success_pattern" having success_rate 0.9
    And the same callback has a pattern "low_success_pattern" having success_rate 0.3
    When get_recommendations is called with current_params {"batch_size": 128}
    Then the returned patterns include "high_success_pattern"
    And the returned patterns do not include "low_success_pattern"

  Scenario: Getting recommendations filters patterns by domain tags
    Given an ACEMLflowCallback for experiment "vision_experiment" with a pattern "cv_pattern" tagged ["computer_vision"] and success_rate 0.8
    And the same callback has a pattern "nlp_pattern" tagged ["nlp"] and success_rate 0.8
    When get_recommendations is called with domain_tags ["computer_vision"]
    Then the returned patterns include "cv_pattern"
    And the returned patterns do not include "nlp_pattern"

  Scenario: Using the callback as a context manager saves knowledge on exit
    Given an ACEMLflowCallback for experiment "vision_experiment" with auto_save disabled
    When the callback is used in a "with" block and a decision is logged inside the block
    And the "with" block exits
    Then the knowledge file on disk contains the logged decision