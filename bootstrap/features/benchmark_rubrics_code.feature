Feature: Code Generation Rubric
  As a caller evaluating an AI-generated Python code submission
  I want to score it across syntax, structure, tests, and security dimensions
  So that I can assess the quality and safety of the generated code

  Background:
    Given a CodeGenerationRubric instance named "code_generation"

  Scenario: Rubric exposes its scoring dimensions and weights
    Then the rubric's dimensions are:
      | name      | weight |
      | syntax    | 0.30   |
      | structure | 0.20   |
      | tests     | 0.30   |
      | security  | 0.20   |
    And the dimension weights sum to 1.0

  Scenario: Well-formed code with docstring, type hints, and a return statement scores highly
    Given the following code:
      """
      def add(a: int, b: int) -> int:
          \"\"\"Add two numbers.\"\"\"
          return a + b
      """
    And no test content is provided in the context
    When the rubric scores the code
    Then the "syntax" dimension score is 100.0
    And the "structure" dimension score is 100.0
    And the "tests" dimension score is 50.0
    And the "security" dimension score is 100.0

  Scenario: Code with invalid Python syntax fails syntax, structure, and tests dimensions
    Given the following code:
      """
      def broken(:
          return
      """
    And no test content is provided in the context
    When the rubric scores the code
    Then the "syntax" dimension score is 0.0
    And the "structure" dimension score is 0.0
    And the "tests" dimension score is 0.0

  Scenario: Code containing a dangerous call scores zero on security regardless of correctness
    Given the following code:
      """
      def run(cmd: str) -> None:
          \"\"\"Run a command.\"\"\"
          os.system(cmd)
      """
    When the rubric scores the code
    Then the "security" dimension score is 0.0

  Scenario: Code free of dangerous calls scores full marks on security
    Given the following code:
      """
      def greet(name: str) -> str:
          return f"hello {name}"
      """
    When the rubric scores the code
    Then the "security" dimension score is 100.0

  Scenario: Minimal function without docstring, annotations, or return statement scores partial structure credit
    Given the following code:
      """
      def do_nothing():
          pass
      """
    When the rubric scores the code
    Then the "structure" dimension score is 25.0

  Scenario: Providing matching test content and a passing implementation scores full marks on tests
    Given the following code:
      """
      def add(a: int, b: int) -> int:
          return a + b
      """
    And the following test content is provided in the context:
      """
      assert add(2, 3) == 5
      """
    When the rubric scores the code
    Then the "tests" dimension score is 100.0

  Scenario: Providing test content that fails against the implementation scores zero on tests
    Given the following code:
      """
      def add(a: int, b: int) -> int:
          return a - b
      """
    And the following test content is provided in the context:
      """
      assert add(2, 3) == 5
      """
    When the rubric scores the code
    Then the "tests" dimension score is 0.0