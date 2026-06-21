Feature: Evaluation Rubric System

  Scenario: Create a scoring dimension with name, weight and description
    Given a scoring dimension with name "Clarity", weight 0.5, and description "How clear the output is"
    When I access the dimension properties
    Then the name should be "Clarity"
    And the weight should be 0.5
    And the description should be "How clear the output is"

  Scenario: Calculate weighted score for a dimension score
    Given a dimension score with dimension "Accuracy", score 80.0, and weight 0.4
    When I access the weightedScore property
    Then the weighted score should be 32.0

  Scenario: Create dimension score with optional notes
    Given a dimension score with dimension "Style", score 90.0, weight 0.3, and notes "Well formatted"
    When I access the notes property
    Then the notes should be "Well formatted"

  Scenario: Create dimension score without notes
    Given a dimension score with dimension "Style", score 90.0, and weight 0.3
    When I access the notes property
    Then the notes should be None

  Scenario: Create rubric result with dimension scores
    Given a dimension score with dimension "Quality", score 75.0, and weight 0.6
    And a dimension score with dimension "Speed", score 85.0, and weight 0.4
    When I create a rubric result with name "TestRubric", totalScore 79.0, and these dimension scores
    Then the rubricName should be "TestRubric"
    And the totalScore should be 79.0
    And the dimensionScores list should contain 2 scores

  Scenario: Rubric result includes empty details dictionary by default
    Given a dimension score with dimension "Quality", score 80.0, and weight 1.0
    When I create a rubric result with name "SimpleRubric", totalScore 80.0, and the dimension score
    Then the details should be an empty dictionary

  Scenario: Score output with concrete rubric implementation clamping scores to 0-100 range
    Given a concrete rubric with name "TestRubric"
    And the rubric has dimension "Correctness" with weight 0.7
    And the rubric has dimension "Style" with weight 0.3
    And the rubric returns raw score 120.0 for "Correctness"
    And the rubric returns raw score -10.0 for "Style"
    When I call score with output "sample code"
    Then the result rubricName should be "TestRubric"
    And the dimension score for "Correctness" should be clamped to 100.0
    And the dimension score for "Style" should be clamped to 0.0
    And the totalScore should be 70.0

  Scenario: Score output with context dictionary
    Given a concrete rubric with name "ContextRubric"
    And the rubric has dimension "Relevance" with weight 1.0
    And the rubric returns score 85.0 for "Relevance" when context contains "testContent"
    When I call score with output "answer text" and context {"testContent": "question"}
    Then the result rubricName should be "ContextRubric"
    And the totalScore should be 85.0
    And the dimensionScores should contain score 85.0 for "Relevance" with weight 1.0