Feature: Experiment Logger
  As a caller of ExperimentLogger, I can log TDD cycles and ML experiments to a
  persistent store and later retrieve them, their statistics, and lessons learned,
  even when the underlying database is unavailable.

  Scenario: Logging a successful TDD cycle records a SUCCESS result
    Given an ExperimentLogger initialized with playbook_version "v1.2"
    When I call log_tdd_cycle with cycle_number 3, requirement "parse CSV headers",
      test_name "test_parses_headers", red_passed False, green_passed True,
      learned_bullets containing 1 bullet, and playbook_id "pb-42"
    Then the returned experiment has experiment_id "tdd_pb-42_cycle_3"
    And the returned experiment has result "SUCCESS"
    And the returned experiment has playbook_updated True

  Scenario: A TDD cycle where the red phase never fails is recorded as an error
    Given an ExperimentLogger initialized with playbook_version "v1.2"
    When I call log_tdd_cycle with cycle_number 5, red_passed True, green_passed True,
      learned_bullets as an empty list, and playbook_id "pb-42"
    Then the returned experiment has result "ERROR"
    And the returned experiment has playbook_updated False

  Scenario: A TDD cycle that never reaches green is recorded as failed
    Given an ExperimentLogger initialized with playbook_version "v1.2"
    When I call log_tdd_cycle with cycle_number 6, red_passed False, green_passed False,
      learned_bullets as an empty list, and playbook_id "pb-42"
    Then the returned experiment has result "FAILED"

  Scenario: An explicit result_override takes precedence over computed result
    Given an ExperimentLogger initialized with playbook_version "v1.2"
    When I call log_tdd_cycle with cycle_number 7, red_passed False, green_passed True,
      result_override "TIMEOUT", learned_bullets as an empty list, and playbook_id "pb-42"
    Then the returned experiment has result "TIMEOUT"

  Scenario: Logging a successful ML experiment with learned patterns
    Given an ExperimentLogger initialized with playbook_version "v2.0"
    When I call log_ml_experiment with experiment_id "ml-exp-9", experiment_name "lr-sweep",
      hyperparameters containing "learning_rate": 0.01, metrics containing "accuracy": 0.95,
      patterns_learned containing 2 patterns, and success True
    Then the returned experiment has experiment_id "ml-exp-9"
    And the returned experiment has result "SUCCESS"
    And the returned experiment has playbook_updated True

  Scenario: Logging a failed ML experiment with no learned patterns
    Given an ExperimentLogger initialized with playbook_version "v2.0"
    When I call log_ml_experiment with experiment_id "ml-exp-10", experiment_name "lr-sweep-2",
      hyperparameters containing "learning_rate": 0.5, metrics containing "accuracy": 0.10,
      patterns_learned as an empty list, and success False
    Then the returned experiment has result "FAILED"
    And the returned experiment has playbook_updated False

  Scenario: Retrieving recent experiments filtered by result
    Given several experiments have been logged with results "SUCCESS", "FAILED", and "SUCCESS"
    When I call get_recent_experiments with limit 10 and result_filter "SUCCESS"
    Then only experiments with result "SUCCESS" are returned

  Scenario: Retrieving experiment statistics summarizes counts and update rate
    Given 4 experiments have been logged, 2 of which set playbook_updated True
    When I call get_experiment_stats
    Then the returned stats include total_experiments 4
    And the returned stats include playbook_updates 2
    And the returned stats include update_rate 0.5

  Scenario: Database unavailability degrades gracefully for read operations
    Given the underlying database connection is unavailable
    When I call get_recent_experiments
    Then an empty list is returned
    When I call get_experiment_stats
    Then a stats dictionary is returned with total_experiments 0 and update_rate 0.0
    When I call get_tdd_lessons
    Then an empty list is returned