Feature: Analysis Rubric Evaluation

  Scenario: Retrieve rubric name
    Given an AnalysisRubric instance
    When the name property is accessed
    Then the name is "analysis"

  Scenario: Retrieve scoring dimensions
    Given an AnalysisRubric instance
    When the dimensions property is accessed
    Then the dimensions list contains 4 items
    And dimension 1 has name "coverage" and weight 0.30
    And dimension 2 has name "reasoning" and weight 0.30
    And dimension 3 has name "accuracy" and weight 0.25
    And dimension 4 has name "citations" and weight 0.15

  Scenario: Score coverage with multiple paragraphs and headings
    Given an AnalysisRubric instance
    When scoring dimension "coverage" with output "This is a long paragraph with more than twenty characters.\n\nThis is another long paragraph with more than twenty characters.\n\n# Introduction\n\nThird paragraph here.\n\n## Section Two\n\nFourth paragraph content."
    Then the score is 100.0

  Scenario: Score coverage with minimal content
    Given an AnalysisRubric instance
    When scoring dimension "coverage" with output "Short text."
    Then the score is 0.0

  Scenario: Score reasoning with multiple logical connectives
    Given an AnalysisRubric instance
    When scoring dimension "reasoning" with output "The results show improvement because the method was refined. However, further testing is needed. Therefore, we conclude that although progress was made, more work remains."
    Then the score is 80.0

  Scenario: Score reasoning with no logical connectives
    Given an AnalysisRubric instance
    When scoring dimension "reasoning" with output "The data shows results. The experiment was completed. The findings are documented."
    Then the score is 0.0

  Scenario: Score accuracy with well-structured sentences
    Given an AnalysisRubric instance
    When scoring dimension "accuracy" with output "This is a well-formed sentence with adequate length. Another sentence follows with proper structure. A third sentence maintains consistent quality and appropriate word count."
    Then the score is 100.0

  Scenario: Score accuracy with insufficient content
    Given an AnalysisRubric instance
    When scoring dimension "accuracy" with output "Too short."
    Then the score is 0.0

  Scenario: Score citations with bracketed reference
    Given an AnalysisRubric instance
    When scoring dimension "citations" with output "The study found significant results [Smith, 2024]."
    Then the score is 100.0

  Scenario: Score citations with URL
    Given an AnalysisRubric instance
    When scoring dimension "citations" with output "More information at https://example.com for details."
    Then the score is 100.0

  Scenario: Score citations with according to phrase
    Given an AnalysisRubric instance
    When scoring dimension "citations" with output "According to recent research, the findings are conclusive."
    Then the score is 100.0

  Scenario: Score citations with no evidence markers
    Given an AnalysisRubric instance
    When scoring dimension "citations" with output "The research shows interesting results without any references."
    Then the score is 0.0

  Scenario: Score unknown dimension returns zero
    Given an AnalysisRubric instance
    When scoring dimension "unknown" with output "Any text content here."
    Then the score is 0.0