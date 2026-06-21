Feature: Reflector Module - Analyze generator performance and extract insights

  Scenario: Successful reflection on a failed task with default settings
    Given a Reflector instance with default settings
    And a TaskInput with id "task-001", query "Calculate 2+2", type "math", and difficulty "easy"
    And a GeneratorOutput with trajectory "I will add the numbers", solution "5", bulletsUsed ["bullet-1", "bullet-2"], and bulletFeedback {}
    And an EnvironmentFeedback with result "FAILED", expected "4", actual "5", and feedback "Incorrect answer"
    When reflect is called with the task, generator output, and environment feedback
    Then a ReflectorOutput is returned
    And the output has errorIdentification populated
    And the output has rootCause populated
    And the output has correctApproach populated
    And the output has keyInsight populated
    And the output has 2 bulletTags
    And each bulletTag has tag "harmful"
    And the output has iterations equal to 1
    And the output has qualityScore between 0.0 and 1.0

  Scenario: Successful reflection on a successful task
    Given a Reflector instance with default settings
    And a TaskInput with id "task-002", query "Sort [3,1,2]", type "coding", and difficulty "medium"
    And a GeneratorOutput with trajectory "Use built-in sort", solution "[1,2,3]", bulletsUsed ["bullet-3"], and bulletFeedback {"bullet-3": "helpful"}
    And an EnvironmentFeedback with result "SUCCESS", expected "[1,2,3]", actual "[1,2,3]", and feedback "All tests passed"
    When reflect is called with the task, generator output, and environment feedback
    Then a ReflectorOutput is returned
    And the output has 1 bulletTag
    And the bulletTag for "bullet-3" has tag "helpful"
    And the output has iterations equal to 1

  Scenario: Iterative refinement disabled produces single iteration
    Given a Reflector instance with enableIterative set to False and maxRefinementRounds set to 5
    And a TaskInput with id "task-003", query "Test query", type "general", and difficulty "hard"
    And a GeneratorOutput with trajectory "reasoning", solution "answer", bulletsUsed [], and bulletFeedback {}
    And an EnvironmentFeedback with result "FAILED", expected "correct", actual "wrong", and feedback "Error occurred"
    When reflect is called with the task, generator output, and environment feedback
    Then a ReflectorOutput is returned
    And the output has iterations equal to 1

  Scenario: High quality analysis stops refinement early
    Given a Reflector instance with enableIterative set to True and maxRefinementRounds set to 5
    And a TaskInput with id "task-004", query "Complex task", type "reasoning", and difficulty "hard"
    And a GeneratorOutput with trajectory "detailed reasoning with multiple steps", solution "comprehensive answer", bulletsUsed ["bullet-4"], and bulletFeedback {}
    And an EnvironmentFeedback with result "FAILED", expected "expected output", actual "actual output", and feedback "Detailed error message explaining what went wrong"
    When reflect is called with the task, generator output, and environment feedback
    Then a ReflectorOutput is returned
    And the output has qualityScore greater than or equal to 0.8
    And the output has iterations less than or equal to 5

  Scenario: Reflection with neutral result tags bullets as neutral
    Given a Reflector instance with default settings
    And a TaskInput with id "task-005", query "Ambiguous task", type "general", and difficulty "medium"
    And a GeneratorOutput with trajectory "attempted solution", solution "result", bulletsUsed ["bullet-5", "bullet-6"], and bulletFeedback {}
    And an EnvironmentFeedback with result "TIMEOUT", expected None, actual None, and feedback "Execution timed out"
    When reflect is called with the task, generator output, and environment feedback
    Then a ReflectorOutput is returned
    And the output has 2 bulletTags
    And each bulletTag has tag "neutral"

  Scenario: Reflection with test report in environment feedback
    Given a Reflector instance with default settings
    And a TaskInput with id "task-006", query "Write function", type "coding", and difficulty "medium"
    And a GeneratorOutput with trajectory "implemented function", solution "def foo(): pass", bulletsUsed ["bullet-7"], and bulletFeedback {}
    And an EnvironmentFeedback with result "FAILED", testReport {"passed": 2, "failed": 3, "total": 5}, and feedback "Some tests failed"
    When reflect is called with the task, generator output, and environment feedback
    Then a ReflectorOutput is returned
    And the output has errorIdentification populated
    And the output has rootCause populated

  Scenario: Get reflector statistics
    Given a Reflector instance with maxRefinementRounds set to 3 and enableIterative set to True
    When getStatistics is called
    Then a dictionary is returned
    And the dictionary contains key "provider"
    And the dictionary contains key "model"
    And the dictionary contains key "maxRefinementRounds" with value 3
    And the dictionary contains key "enableIterative" with value True

  Scenario: Reflection preserves generator bullet feedback tags
    Given a Reflector instance with default settings
    And a TaskInput with id "task-007", query "Task with feedback", type "general", and difficulty "easy"
    And a GeneratorOutput with trajectory "reasoning", solution "answer", bulletsUsed ["bullet-8", "bullet-9"], and bulletFeedback {"bullet-8": "helpful", "bullet-9": "neutral"}
    And an EnvironmentFeedback with result "SUCCESS", expected "answer", actual "answer", and feedback None
    When reflect is called with the task, generator output, and environment feedback
    Then a ReflectorOutput is returned
    And the bulletTag for "bullet-8" has tag "helpful"
    And the bulletTag for "bullet-9" has tag "neutral"