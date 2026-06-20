Feature: Blind Evaluation
  Evaluates submissions without revealing agent identity

  Scenario: Evaluate submission with valid syntax and no tests
    Given a submission with taskId "task-001" and submissionId "sub-alpha"
    And the outputType is "code"
    And the outputContent is valid Python code "def add(a, b):\n    return a + b"
    And no testContent is provided
    When the evaluator evaluates the submission
    Then the result submissionId is "sub-alpha"
    And the qualityScore is 55
    And testsPassed is None
    And details contains syntaxValid as True
    And details contains structureScore as 5

  Scenario: Evaluate submission with invalid syntax
    Given a submission with taskId "task-002" and submissionId "sub-beta"
    And the outputType is "code"
    And the outputContent is invalid Python code "def broken(\n    return"
    And no testContent is provided
    When the evaluator evaluates the submission
    Then the result submissionId is "sub-beta"
    And the qualityScore is 0
    And testsPassed is None
    And details contains syntaxValid as False

  Scenario: Evaluate submission with passing tests
    Given a submission with taskId "task-003" and submissionId "sub-gamma"
    And the outputType is "code"
    And the outputContent is "def multiply(x, y):\n    return x * y"
    And the testContent is "def test_multiply():\n    assert multiply(2, 3) == 6"
    When the evaluator evaluates the submission
    Then the result submissionId is "sub-gamma"
    And the qualityScore is 85
    And testsPassed is True
    And details contains syntaxValid as True

  Scenario: Evaluate submission with well-structured code
    Given a submission with taskId "task-004" and submissionId "sub-delta"
    And the outputType is "code"
    And the outputContent is "def greet(name: str) -> str:\n    \"\"\"Greet someone.\"\"\"\n    return f'Hello {name}'"
    And no testContent is provided
    When the evaluator evaluates the submission
    Then the result submissionId is "sub-delta"
    And the qualityScore is 70
    And testsPassed is None
    And details contains structureScore as 20

  Scenario: Evaluate multiple runs of the same task
    Given 3 submissions all with taskId "task-005"
    And submission 1 has submissionId "sub-e1" with qualityScore 80
    And submission 2 has submissionId "sub-e2" with qualityScore 90
    And submission 3 has submissionId "sub-e3" with qualityScore 70
    When the evaluator evaluates multi-run for these submissions
    Then the multi-run result taskId is "task-005"
    And the meanScore is 80.0
    And the stdDev is greater than 0
    And the varianceCoefficient is calculated as stdDev divided by meanScore
    And the results list contains 3 evaluation results

  Scenario: Evaluate multi-run with empty submissions list
    Given an empty list of submissions
    When the evaluator evaluates multi-run for these submissions
    Then a ValueError is raised with message "submissions must not be empty"

  Scenario: Evaluate multi-run with mixed task IDs
    Given 2 submissions with different taskIds
    And submission 1 has taskId "task-006" and submissionId "sub-f1"
    And submission 2 has taskId "task-007" and submissionId "sub-f2"
    When the evaluator evaluates multi-run for these submissions
    Then a ValueError is raised indicating mixed taskIds

  Scenario: Evaluate submission using domain rubric
    Given a submission with taskId "task-008" and submissionId "sub-eta"
    And the outputType is "tests"
    And a rubric is registered for outputType "tests"
    And the outputContent matches rubric criteria
    When the evaluator evaluates the submission
    Then the result submissionId is "sub-eta"
    And the qualityScore is determined by the rubric
    And the rubricName is set to the registered rubric name
    And details contains rubricDimensions with scores and weights