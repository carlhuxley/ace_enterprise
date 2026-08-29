Feature: Analysis Rubric evaluation
  As a caller of the benchmark evaluation system
  I want to score analytical/research output across weighted dimensions
  So that I can measure the quality of analytical text

  Scenario: Rubric identifies itself as "analysis"
    Given an instance of the analysis rubric
    When I request its name
    Then the name should be "analysis"

  Scenario: Rubric exposes four weighted dimensions summing to 1.0
    Given an instance of the analysis rubric
    When I request its scoring dimensions
    Then it should return dimensions "coverage", "reasoning", "accuracy", and "citations"
    And the dimension weights should be 0.30, 0.30, 0.25, and 0.15 respectively
    And the dimension weights should sum to 1.0

  Scenario: Well-structured output with headings and multiple paragraphs scores full coverage
    Given the following output:
      """
      ## Introduction

      This section introduces the analysis topic in enough detail to count.

      ## Findings

      Here we describe the first major finding in sufficient depth to qualify.

      ## Discussion

      This paragraph discusses implications at length for the reader.

      ## Conclusion

      This final paragraph wraps up the analysis with a summary statement.
      """
    When the output is scored on the "coverage" dimension
    Then the coverage score should be 100.0

  Scenario: Output with no paragraph breaks or headings scores zero coverage
    Given the following output:
      """
      A single short line of text with no blank-line breaks.
      """
    When the output is scored on the "coverage" dimension
    Then the coverage score should be 0.0

  Scenario: Output rich in logical connectives scores full reasoning
    Given the following output:
      """
      The results improved because the sample size increased. Therefore,
      confidence grew. However, some outliers remained. Consequently, the
      team investigated further. As a result, the model was revised.
      """
    When the output is scored on the "reasoning" dimension
    Then the reasoning score should be 100.0

  Scenario: Output with no logical connectives scores zero reasoning
    Given the following output:
      """
      The sample size increased. Confidence grew. Outliers remained.
      """
    When the output is scored on the "reasoning" dimension
    Then the reasoning score should be 0.0

  Scenario: Output with citation markers scores full citations
    Given the following output:
      """
      According to recent findings [Smith, 2024], the trend continued.
      """
    When the output is scored on the "citations" dimension
    Then the citations score should be 100.0

  Scenario: Output with no citation markers scores zero citations
    Given the following output:
      """
      The trend continued without any supporting evidence mentioned.
      """
    When the output is scored on the "citations" dimension
    Then the citations score should be 0.0