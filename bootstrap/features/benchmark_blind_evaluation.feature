Feature: Blind evaluation of submissions
  As a caller of the benchmark system
  I want submissions scored without knowledge of which agent produced them
  So that evaluation results remain free of agent-identity bias

  Scenario: Evaluating syntactically valid code with no tests
    Given a submission with task_id "task-1", submission_id "sub-abc", output_type "code"
    And output_content "def add(a, b):\n    return a + b\n"
    And no test_content is provided
    When the submission is evaluated
    Then the result's submission_id is "sub-abc"
    And tests_passed is None
    And quality_score is greater than 0 and less than or equal to 100

  Scenario: Evaluating code with invalid syntax
    Given a submission with task_id "task-2", submission_id "sub-bad", output_type "code"
    And output_content "def broken(:\n    pass"
    When the submission is evaluated
    Then the result's submission_id is "sub-bad"
    And quality_score is less than 30
    And tests_passed is None

  Scenario: Evaluating code with tests that pass
    Given a submission with task_id "task-3", submission_id "sub-pass", output_type "code"
    And output_content "def add(a, b):\n    return a + b\n"
    And test_content "assert add(2, 3) == 5"
    When the submission is evaluated
    Then tests_passed is True
    And quality_score is greater than or equal to 50

  Scenario: Evaluating code with tests that fail
    Given a submission with task_id "task-4", submission_id "sub-fail", output_type "code"
    And output_content "def add(a, b):\n    return a - b\n"
    And test_content "assert add(2, 3) == 5"
    When the submission is evaluated
    Then tests_passed is False
    And the result's details contain test execution information

  Scenario: Evaluating a submission whose output_type has a registered domain rubric
    Given a submission with task_id "task-5", submission_id "sub-rubric", output_type "docs"
    And output_content "# API Documentation\n\nThis module does X."
    And the "docs" output_type has a registered rubric named "documentation_rubric"
    When the submission is evaluated
    Then the result's rubric_name is "documentation_rubric"
    And quality_score reflects the rubric's total_score

  Scenario: Evaluating multiple submissions for the same task reports score variance
    Given three submissions all with task_id "task-6" and submission_ids "sub-1", "sub-2", "sub-3"
    And output_type "code" for each
    When the submissions are evaluated as a multi-run batch
    Then a MultiRunResult is returned with task_id "task-6"
    And it contains one EvaluationResult per submission
    And mean_score equals the average of the individual quality_scores
    And variance_coefficient is 0 when mean_score is 0
    And consistency_rate reflects the fraction of runs agreeing with the majority pass/fail outcome

  Scenario: Requesting a multi-run evaluation with no submissions
    Given an empty list of submissions
    When a multi-run evaluation is requested
    Then a ValueError is raised

  Scenario: Requesting a multi-run evaluation with submissions from different tasks
    Given a submission with task_id "task-7" and submission_id "sub-x"
    And a submission with task_id "task-8" and submission_id "sub-y"
    When a multi-run evaluation is requested with both submissions
    Then a ValueError is raised