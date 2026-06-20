Feature: Code Generation Rubric
  Evaluates Python code output across syntax, structure, tests, and security dimensions

  Scenario: Rubric identifies itself with a name
    Given a CodeGenerationRubric instance
    When the name property is accessed
    Then the name is "code_generation"

  Scenario: Rubric defines four weighted scoring dimensions
    Given a CodeGenerationRubric instance
    When the dimensions property is accessed
    Then there are 4 dimensions
    And dimension "syntax" has weight 0.30
    And dimension "structure" has weight 0.20
    And dimension "tests" has weight 0.30
    And dimension "security" has weight 0.20

  Scenario: Valid Python syntax scores 100 on syntax dimension
    Given a CodeGenerationRubric instance
    When evaluating dimension "syntax" with output "def hello():\n    return 'world'"
    Then the score is 100.0

  Scenario: Invalid Python syntax scores 0 on syntax dimension
    Given a CodeGenerationRubric instance
    When evaluating dimension "syntax" with output "def hello(\n    return 'world'"
    Then the score is 0.0

  Scenario: Code with function, docstring, type hints, and return scores 100 on structure
    Given a CodeGenerationRubric instance
    When evaluating dimension "structure" with output "def add(x: int, y: int) -> int:\n    \"\"\"Add two numbers.\"\"\"\n    return x + y"
    Then the score is 100.0

  Scenario: Code with no functions scores 0 on structure dimension
    Given a CodeGenerationRubric instance
    When evaluating dimension "structure" with output "x = 42\nprint(x)"
    Then the score is 0.0

  Scenario: Code with function but no docstring, type hints, or return scores 25 on structure
    Given a CodeGenerationRubric instance
    When evaluating dimension "structure" with output "def hello():\n    print('hi')"
    Then the score is 25.0

  Scenario: Security dimension scores 100 when no dangerous patterns present
    Given a CodeGenerationRubric instance
    When evaluating dimension "security" with output "def safe():\n    return 42"
    Then the score is 100.0

  Scenario: Security dimension scores 0 when eval is present
    Given a CodeGenerationRubric instance
    When evaluating dimension "security" with output "def unsafe():\n    eval('1+1')"
    Then the score is 0.0

  Scenario: Security dimension scores 0 when exec is present
    Given a CodeGenerationRubric instance
    When evaluating dimension "security" with output "exec('print(1)')"
    Then the score is 0.0

  Scenario: Security dimension scores 0 when os.system is present
    Given a CodeGenerationRubric instance
    When evaluating dimension "security" with output "import os\nos.system('ls')"
    Then the score is 0.0

  Scenario: Tests dimension scores 50 when no test content provided but code is valid
    Given a CodeGenerationRubric instance
    When evaluating dimension "tests" with output "def add(x, y):\n    return x + y" and context {}
    Then the score is 50.0

  Scenario: Tests dimension scores 0 when no test content provided and code is invalid
    Given a CodeGenerationRubric instance
    When evaluating dimension "tests" with output "def add(x, y\n    return x + y" and context {}
    Then the score is 0.0

  Scenario: Overall score combines all dimensions with their weights
    Given a CodeGenerationRubric instance
    When evaluating output "def add(x: int, y: int) -> int:\n    \"\"\"Add.\"\"\"\n    return x + y" with context {}
    Then the overall score reflects weighted combination of syntax 100.0, structure 100.0, tests 50.0, and security 100.0