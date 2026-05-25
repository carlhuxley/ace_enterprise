Feature: LanguagePod protocol

  Scenario: run_red returns a failing PhaseResult
    Given a PodSpec with feature_requirement "add two numbers", test_file "test_add.py", implementation_file "add.py", and cycle_number 1
    When the pod executes run_red with that spec
    Then the returned PhaseResult has passed equal to False

  Scenario: run_green returns a passing PhaseResult
    Given a PodSpec with feature_requirement "add two numbers", test_file "test_add.py", implementation_file "add.py", and cycle_number 1
    When the pod executes run_green with that spec
    Then the returned PhaseResult has passed equal to True

  Scenario: run_refactor returns a passing PhaseResult
    Given a PodSpec with feature_requirement "add two numbers", test_file "test_add.py", implementation_file "add.py", and cycle_number 1
    When the pod executes run_refactor with that spec
    Then the returned PhaseResult has passed equal to True

  Scenario: run_red includes output and no error
    Given a PodSpec with feature_requirement "subtract two numbers", test_file "test_sub.py", implementation_file "sub.py", and cycle_number 2
    When the pod executes run_red with that spec
    Then the returned PhaseResult has output as a non-empty string
    And the returned PhaseResult has error equal to None

  Scenario: run_green includes output and no error
    Given a PodSpec with feature_requirement "subtract two numbers", test_file "test_sub.py", implementation_file "sub.py", and cycle_number 2
    When the pod executes run_green with that spec
    Then the returned PhaseResult has output as a non-empty string
    And the returned PhaseResult has error equal to None

  Scenario: run_refactor includes output and no error
    Given a PodSpec with feature_requirement "subtract two numbers", test_file "test_sub.py", implementation_file "sub.py", and cycle_number 2
    When the pod executes run_refactor with that spec
    Then the returned PhaseResult has output as a non-empty string
    And the returned PhaseResult has error equal to None

  Scenario: token_usage returns a list ordered by cycle_number
    Given a pod that has executed at least one cycle
    When the pod returns token_usage
    Then the result is a list of TokenUsage objects
    And the list is ordered by cycle_number in ascending order

  Scenario: run_red with error_output from previous failure
    Given a PodSpec with feature_requirement "multiply two numbers", test_file "test_mul.py", implementation_file "mul.py", cycle_number 3, and error_output "AssertionError: expected 6 but got 5"
    When the pod executes run_red with that spec
    Then the returned PhaseResult has passed equal to False