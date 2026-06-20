Feature: Module Architect - Generate module-level contracts for stateful systems

  Scenario: Generate a basic module contract without context
    Given a requirement "Create an inventory system with add_item and get_total_value functions"
    When I call generateModuleContract with the requirement
    Then the result success is True
    And the contract contains a module with name "inventory"
    And the contract contains 2 functions
    And the contract contains at least 1 integration test
    And the contract has a complexity value greater than 0

  Scenario: Generate module contract with codebase context
    Given a codebase context with existing function "get_db() -> Connection" in module "database"
    And the context includes schema table "applications" with columns "id, name, status"
    And the context includes pattern "Use get_db() for database connections"
    When I call generateModuleContract with requirement "Add search functionality for applications" and the context
    Then the result success is True
    And the contract dependencies dependsOn includes "get_db"
    And the contract dependencies tablesRead includes "applications"
    And the audit event payload hasContext is True

  Scenario: Extract context from a Python file
    Given a Python file containing function "def create_user(name: str) -> dict:" with docstring "Create a new user"
    And the file contains SQL "SELECT * FROM users WHERE id = ?"
    And the file contains SQL "INSERT INTO profiles (user_id, bio) VALUES (?, ?)"
    When I call extractContextFromFile with the file path
    Then the context existingFunctions contains "create_user" with signature "(name: str) -> dict"
    And the context schema contains table "users"
    And the context schema contains table "profiles"
    And the context patterns includes "Return dict for single records"

  Scenario: Extract context from directory with multiple files
    Given a directory containing "users.py" with function "get_user(id: int) -> dict"
    And the directory contains "posts.py" with SQL "CREATE TABLE posts (id, title, content)"
    When I call extractContextFromDirectory with the directory path
    Then the combined context existingFunctions contains "get_user"
    And the combined context schema contains table "posts"

  Scenario: Validate module implementation against contract
    Given a module contract with function "add(x: int, y: int) -> int"
    And the contract has integration test with steps "result = add(2, 3)" and assertion "result == 5"
    And implementation code "def add(x: int, y: int) -> int:\n    return x + y"
    When I call validateModule with the contract and code
    Then validation returns True
    And the failure list is empty

  Scenario: Validation fails when function is missing
    Given a module contract with function "multiply(x: int, y: int) -> int"
    And implementation code "def add(x: int, y: int) -> int:\n    return x + y"
    When I call validateModule with the contract and code
    Then validation returns False
    And the failure list contains "Function 'multiply' not found"

  Scenario: Validation fails when assertion does not pass
    Given a module contract with function "calculate() -> int"
    And the contract has integration test with steps "result = calculate()" and assertion "result == 10"
    And implementation code "def calculate() -> int:\n    return 5"
    When I call validateModule with the contract and code
    Then validation returns False
    And the failure list contains "assertion failed"

  Scenario: Generate implementation prompt from contract
    Given a module contract with sharedState "counter: int = 0"
    And the contract has function "increment() -> None" with docstring "Increment counter"
    And the contract has integration test "test_increment" with setup "counter = 0" and assertion "counter == 1"
    And the contract has hint "Use global counter variable"
    When I call generateModulePrompt with the contract
    Then the prompt contains "Shared state:"
    And the prompt contains "counter: int = 0"
    And the prompt contains "def increment() -> None:"
    And the prompt contains "test_increment"
    And the prompt contains "Use global counter variable"