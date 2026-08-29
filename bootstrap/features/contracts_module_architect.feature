Feature: Module Architect
  As a caller building stateful Python modules from requirements,
  I want to generate module-level contracts, render implementation prompts,
  extract codebase context, and validate implementations against integration tests.

  Scenario: Generate a module contract from a plain requirement
    Given a requirement "Simple inventory management system"
    And an LLM client that returns valid JSON describing a module named "inventory" with functions "add_item" and "get_total_value" and two integration tests
    When I call generate_module_contract with the requirement
    Then the result's success flag is True
    And the result's contract name is "inventory"
    And the contract contains 2 functions
    And the contract contains 2 integration tests

  Scenario: Generate a module contract with codebase context to reuse existing functions
    Given a requirement "Add search to applications"
    And a CodebaseContext with an existing function "get_application(id: int) -> dict" and a schema table "applications" with columns "id, name, role"
    And an LLM client that returns valid JSON describing a module "feature_name" with a dependencies block listing depends_on "get_application" and tables_read "applications"
    When I call generate_module_contract with the requirement and the context
    Then the result's success flag is True
    And the contract's dependencies.depends_on includes "get_application"
    And the contract's dependencies.tables_read includes "applications"

  Scenario: LLM response missing JSON causes a failed result instead of raising
    Given a requirement "Do something"
    And an LLM client that returns the plain text "I cannot help with that"
    When I call generate_module_contract with the requirement
    Then the result's success flag is False
    And the result's contract is None
    And the result's error message is not empty

  Scenario: Dependencies default to declared function names when omitted
    Given an LLM response JSON describing a module with functions "compute" and no "dependencies" key
    When I call generate_module_contract with a requirement that yields this response
    Then the result's contract dependencies.provides equals ["compute"]
    And the result's contract dependencies.depends_on is an empty list

  Scenario: Render an implementation prompt from a generated contract
    Given a ModuleContract with shared_state "inventory: dict[str, dict] = {}" and one function "add_item(name: str, quantity: int, price: float) -> None"
    And one integration test "test_add_and_get_value" with setup "inventory.clear()" and assertion "result == 18.75"
    When I call generate_module_prompt with the contract
    Then the returned prompt text includes the shared state code
    And the returned prompt text includes the function signature "add_item(name: str, quantity: int, price: float) -> None"
    And the returned prompt text includes the assertion "result == 18.75"
    And the returned prompt text instructs to respond with only Python code and no test code

  Scenario: Extract codebase context from a single Python file
    Given a Python file "db.py" containing a function "get_db()" with a docstring "Get a database connection" and a SQL string "SELECT * FROM applications WHERE id = ?"
    When I call extract_context_from_file with the path to "db.py"
    Then the returned CodebaseContext's existing_functions includes a function named "get_db"
    And the returned CodebaseContext's schema includes a table named "applications"
    And the returned CodebaseContext's patterns includes "Use get_db() for database connections"

  Scenario: Extract and merge codebase context from a directory of Python files
    Given a directory containing "users.py" with a function "create_user(name: str) -> dict" and "orders.py" with a function "create_order(user_id: int) -> dict"
    When I call extract_context_from_directory with the directory path
    Then the returned CodebaseContext's existing_functions includes both "create_user" and "create_order"
    And files whose names start with "__" are excluded from extraction

  Scenario: Validate a correct module implementation reports success
    Given a ModuleContract requiring a function "add_item" and an integration test "test_add_and_get_value" with assertion "result == 18.75"
    And working Python source code implementing "add_item" and "get_total_value" that satisfies the assertion
    When I call validate_module with the contract and the code
    Then the returned all_passed flag is True
    And the returned list of failure messages is empty

  Scenario: Validate an implementation missing a required function reports failure
    Given a ModuleContract requiring a function "get_total_value"
    And Python source code that does not define "get_total_value"
    When I call validate_module with the contract and the code
    Then the returned all_passed flag is False
    And the returned list of failure messages includes an entry mentioning "get_total_value"