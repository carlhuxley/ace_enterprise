Feature: Test Writing Rubric Evaluation

  Scenario: Rubric identifies itself with a name
    Given a TestWritingRubric instance
    When the name property is accessed
    Then the name is "testWriting"

  Scenario: Rubric defines four weighted scoring dimensions
    Given a TestWritingRubric instance
    When the dimensions property is accessed
    Then there are 4 dimensions
    And dimension "edgeCases" has weight 0.30 and description "Boundary conditions tested"
    And dimension "assertions" has weight 0.30 and description "Assert density relative to test count"
    And dimension "naming" has weight 0.20 and description "Descriptive test function names"
    And dimension "coverage" has weight 0.20 and description "Multiple independent test functions"

  Scenario: Edge cases dimension scores based on boundary pattern matches
    Given a TestWritingRubric instance
    When scoring dimension "edgeCases" with code "testValue = None; check([]); x = 0"
    Then the score is 60.0

  Scenario: Edge cases dimension caps score at 100
    Given a TestWritingRubric instance
    When scoring dimension "edgeCases" with code "None [] {} '' \"\" 0 -1 empty boundary invalid negative overflow zero extra"
    Then the score is 100.0

  Scenario: Assertions dimension scores ratio of asserts to test functions
    Given a TestWritingRubric instance
    When scoring dimension "assertions" with code containing 2 test functions and 4 assert statements
    Then the score is 100.0

  Scenario: Assertions dimension returns zero for non-test functions
    Given a TestWritingRubric instance
    When scoring dimension "assertions" with code "def helper(): assert True"
    Then the score is 0.0

  Scenario: Assertions dimension returns zero for syntax errors
    Given a TestWritingRubric instance
    When scoring dimension "assertions" with code "def testBad( invalid syntax"
    Then the score is 0.0

  Scenario: Naming dimension scores descriptive multi-word test names
    Given a TestWritingRubric instance
    When scoring dimension "naming" with code containing test functions "testAddTwoNumbers" and "testX"
    Then the score is 50.0

  Scenario: Naming dimension returns zero when no test functions exist
    Given a TestWritingRubric instance
    When scoring dimension "naming" with code "def helper(): pass"
    Then the score is 0.0

  Scenario: Coverage dimension scores based on test function count
    Given a TestWritingRubric instance
    When scoring dimension "coverage" with code containing 0 test functions
    Then the score is 0.0

  Scenario: Coverage dimension awards partial credit for few tests
    Given a TestWritingRubric instance
    When scoring dimension "coverage" with code containing 1 test function
    Then the score is 40.0

  Scenario: Coverage dimension increases score with more tests
    Given a TestWritingRubric instance
    When scoring dimension "coverage" with code containing 3 test functions
    Then the score is 80.0

  Scenario: Coverage dimension caps at 100 for five or more tests
    Given a TestWritingRubric instance
    When scoring dimension "coverage" with code containing 5 test functions
    Then the score is 100.0

  Scenario: Unknown dimension returns zero score
    Given a TestWritingRubric instance
    When scoring dimension "unknownDimension" with any code
    Then the score is 0.0
