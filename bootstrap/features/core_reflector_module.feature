Feature: Reflector task analysis and bullet feedback tagging

  As a caller of the Reflector module
  I want to analyze task execution outcomes
  So that I receive structured insights and feedback tags for bullets used

  Scenario: Successful task reflection tags used bullets as helpful by default
    Given a task with id "task-42" and query "Sort a list of integers"
    And a generator output that used bullets ["bullet-1", "bullet-2"] with no explicit bullet feedback
    And environment feedback with result "SUCCESS"
    When I call reflect with the task, generator output, and environment feedback
    Then the returned output tags bullet "bullet-1" as "helpful"
    And the returned output tags bullet "bullet-2" as "helpful"

  Scenario: Failed task reflection tags used bullets as harmful by default
    Given a task with id "task-43" and query "Reverse a string"
    And a generator output that used bullets ["bullet-3"] with no explicit bullet feedback
    And environment feedback with result "FAILED" and feedback "AssertionError: expected 'cba', got 'abc'"
    When I call reflect with the task, generator output, and environment feedback
    Then the returned output tags bullet "bullet-3" as "harmful"

  Scenario: Explicit bullet feedback from the generator overrides the default tag
    Given a task with id "task-44" and query "Compute factorial of 5"
    And a generator output that used bullets ["bullet-5"] with bullet feedback {"bullet-5": "neutral"}
    And environment feedback with result "FAILED"
    When I call reflect with the task, generator output, and environment feedback
    Then the returned output tags bullet "bullet-5" as "neutral"

  Scenario: Reflection result other than SUCCESS or FAILED tags bullets as neutral
    Given a task with id "task-45" and query "Parse a malformed config file"
    And a generator output that used bullets ["bullet-6"] with no explicit bullet feedback
    And environment feedback with result "ERROR"
    When I call reflect with the task, generator output, and environment feedback
    Then the returned output tags bullet "bullet-6" as "neutral"

  Scenario: Reflection output includes analysis fields and a quality score
    Given a task with id "task-46" and query "Compute the median of a list"
    And a generator output with trajectory "Sorted the list and took the middle element" and solution "return sorted(nums)[len(nums)//2]"
    And environment feedback with result "FAILED" and expected "3.5" and actual "4"
    When I call reflect with the task, generator output, and environment feedback
    Then the returned output includes a non-empty error identification
    And the returned output includes a root cause
    And the returned output includes a correct approach
    And the returned output includes a key insight
    And the returned output includes a quality score between 0.0 and 1.0
    And the returned output includes an iteration count of at least 1

  Scenario: Iterative refinement is disabled so reflection completes in a single iteration
    Given a Reflector configured with iterative refinement disabled
    And a task with id "task-47" and query "Check if a number is prime"
    And a generator output that used bullets ["bullet-7"]
    And environment feedback with result "SUCCESS"
    When I call reflect with the task, generator output, and environment feedback
    Then the returned output reports an iteration count of 1

  Scenario: Retrieving reflector statistics exposes its configuration
    Given a Reflector configured with max refinement rounds set to 3 and iterative refinement enabled
    When I call get_statistics
    Then the returned statistics include the LLM provider name
    And the returned statistics include the LLM model name
    And the returned statistics report max_refinement_rounds as 3
    And the returned statistics report enable_iterative as true