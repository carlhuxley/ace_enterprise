Feature: Domain-specific evaluation rubric scoring

  Scenario: Scoring an output produces a weighted total across all dimensions
    Given a rubric named "CodeQualityRubric" with dimensions:
      | name          | weight | description                  |
      | correctness   | 0.6    | Does the code work correctly |
      | readability   | 0.4    | Is the code easy to read     |
    And the rubric scores "correctness" as 80 and "readability" as 50 for the given output
    When I call score("def add(a, b): return a + b") on the rubric
    Then the result's rubric_name is "CodeQualityRubric"
    And the result's total_score is 68.0
    And the result's dimension_scores contains a DimensionScore with dimension "correctness", score 80, and weight 0.6
    And the result's dimension_scores contains a DimensionScore with dimension "readability", score 50, and weight 0.4

  Scenario: A dimension score above 100 is clamped to 100
    Given a rubric named "OverflowRubric" with a single dimension "coverage" weighted 1.0
    And the rubric's raw score for "coverage" is 150
    When I call score("some output") on the rubric
    Then the result's dimension_scores contains a DimensionScore with dimension "coverage" and score 100.0
    And the result's total_score is 100.0

  Scenario: A dimension score below 0 is clamped to 0
    Given a rubric named "UnderflowRubric" with a single dimension "safety" weighted 1.0
    And the rubric's raw score for "safety" is -25
    When I call score("some output") on the rubric
    Then the result's dimension_scores contains a DimensionScore with dimension "safety" and score 0.0
    And the result's total_score is 0.0

  Scenario: Passing optional context metadata is available when scoring dimensions
    Given a rubric named "TestAwareRubric" with a single dimension "test_alignment" weighted 1.0
    And the rubric uses the "test_content" key from context to determine its score
    When I call score("def sub(a, b): return a - b", context={"test_content": "assert sub(2, 1) == 1"}) on the rubric
    Then the result's total_score reflects the score computed using the supplied context

  Scenario: Omitting context defaults to an empty context dict
    Given a rubric named "NoContextRubric" with a single dimension "style" weighted 1.0
    When I call score("some output") on the rubric without a context argument
    Then scoring completes successfully and returns a RubricResult

  Scenario: A DimensionScore exposes its weighted score
    Given a DimensionScore with dimension "correctness", score 80, and weight 0.6
    When I access its weighted_score property
    Then the weighted_score is 48.0

  Scenario: Calling score() on the base EvaluationRubric without a name raises an error
    Given a bare EvaluationRubric instance with no overridden "name" property
    When I access the "name" property
    Then a NotImplementedError is raised

  Scenario: Calling score() on a rubric that has not implemented dimension scoring raises an error
    Given a rubric that defines "name" and "dimensions" but does not override the dimension-scoring behavior
    When I call score("some output") on the rubric
    Then a NotImplementedError is raised