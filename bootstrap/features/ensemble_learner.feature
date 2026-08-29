Feature: Ensemble Learner orchestrates multiple LLM models to learn collaboratively

  Scenario: Initializing an ensemble learner tracks performance for every configured model
    Given an ensemble learner is configured with models [("togetherai", "Qwen2.5-72B"), ("ollama", "llama3.1")] for playbook "playbook-42"
    When the ensemble learner is initialized
    Then the model performance tracker contains an entry for "togetherai/Qwen2.5-72B"
    And the model performance tracker contains an entry for "ollama/llama3.1"

  Scenario: Running a full learning cycle returns a consensus result with approved and rejected bullets
    Given an ensemble learner configured with 2 models for playbook "playbook-42"
    And a task input describing "add input validation to the login form"
    And environment feedback indicating the task succeeded
    When learn_from_task is called with the task and environment feedback
    Then the returned EnsembleResult lists both models in "models_used"
    And the result contains a "bullets" list of consensus bullets
    And the result reports a "started_at" time before its "completed_at" time
    And the result includes numeric "diversity_score" and "consensus_strength" values

  Scenario: Each proposed bullet accumulates one vote per model in the ensemble
    Given an ensemble learner configured with 3 models for playbook "playbook-42"
    And a task input describing "fix off-by-one error in pagination"
    And environment feedback indicating the task failed
    When learn_from_task is called with the task and environment feedback
    Then every bullet in the result has been voted on by all 3 models
    And the result's "vote_results" reports the total number of bullets voted on

  Scenario: Learning from a task can run models sequentially instead of in parallel
    Given an ensemble learner configured with 2 models for playbook "playbook-42"
    And a task input describing "refactor the payment retry logic"
    And environment feedback indicating the task succeeded
    When learn_from_task is called with parallel set to False
    Then an EnsembleResult is still returned with bullets, vote_results, and model_performance populated

  Scenario: Approved bullets from a completed ensemble result are added to the shared playbook
    Given an ensemble learning cycle has completed and produced an EnsembleResult with 2 approved bullets
    And each approved bullet's "proposed_by" field is a valid "provider/model" identifier such as "togetherai/Qwen2.5-72B"
    When add_approved_bullets_to_playbook is called with that result
    Then 2 bullets are added to the playbook identified by "playbook-42"
    And the number of bullets added is returned to the caller

  Scenario: A bullet proposed by a model with an unrecognized provider is skipped when adding to the playbook
    Given an EnsembleResult contains one approved bullet whose "proposed_by" is "unknown-provider/some-model"
    When add_approved_bullets_to_playbook is called with that result
    Then that bullet is not added to the playbook
    And the returned count of added bullets does not include the skipped bullet

  Scenario: A model that fails during the learning cycle does not prevent the ensemble from producing a result
    Given an ensemble learner configured with 2 models for playbook "playbook-42"
    And one of the configured models will raise an error when executed
    And a task input describing "update the caching layer"
    And environment feedback indicating the task succeeded
    When learn_from_task is called with the task and environment feedback
    Then an EnsembleResult is still returned
    And the failing model contributes zero proposals to the result