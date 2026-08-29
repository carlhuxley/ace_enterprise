Feature: Contract Architect generates function contracts from natural language requirements

  Scenario: Generating contracts from a well-formed LLM response wrapped in markdown
    Given an LLM client that responds with:
      """
      {"contracts": [{"id": "feat-001", "function_name": "calculate_total", "signature": "(items: list[float], tax_rate: float) -> float", "docstring": "Calculate total price including tax", "complexity": 2, "test_cases": [{"name": "basic", "input": "([10.0, 20.0], 0.1)", "expected": "33.0"}], "hints": ["Sum items first"]}]}
      """
    And a ContractArchitect configured with that LLM client
    When I call generate_contracts with requirement "Calculate order total with tax"
    Then the result's success flag is True
    And the result contains exactly 1 contract
    And the contract's function_name is "calculate_total"
    And the contract's complexity is 2
    And the contract has 1 test case named "basic" with expected value "33.0"

  Scenario: Generating contracts from a raw JSON response with no markdown fences
    Given an LLM client that responds with:
      """
      {"contracts": [{"id": "feat-002", "function_name": "get_total_value", "signature": "() -> float", "docstring": "Get total inventory value", "complexity": 3, "test_cases": [{"name": "empty", "input": "()", "expected": "0.0"}]}]}
      """
    And a ContractArchitect configured with that LLM client
    When I call generate_contracts with requirement "Get inventory value"
    Then the result's success flag is True
    And the result contains exactly 1 contract
    And the contract's function_name is "get_total_value"

  Scenario: A contract for a stateful function includes setup and teardown fixtures
    Given an LLM client that responds with a contract for "get_total_value" that includes fixtures with setup "global inventory; inventory = {}" and teardown "inventory.clear()"
    And a ContractArchitect configured with that LLM client
    When I call generate_contracts with requirement "Get inventory value across calls"
    Then the result's success flag is True
    And the returned contract has fixtures
    And the fixture's teardown is "inventory.clear()"

  Scenario: LLM response contains no parsable JSON
    Given an LLM client that responds with "I could not decompose this requirement."
    And a ContractArchitect configured with that LLM client
    When I call generate_contracts with requirement "Do something vague"
    Then the result's success flag is False
    And the result contains no contracts
    And the result's error message mentions "No JSON found"

  Scenario: LLM response contains malformed JSON
    Given an LLM client that responds with:
      """
      {"contracts": [{"id": "feat-003", "function_name": "broken",]}
      """
    And a ContractArchitect configured with that LLM client
    When I call generate_contracts with requirement "Broken requirement"
    Then the result's success flag is False
    And the result's error message mentions "Invalid JSON"

  Scenario: The same requirement always produces the same requirement hash
    Given an LLM client that responds with a valid single-contract JSON payload
    And a ContractArchitect configured with that LLM client
    When I call generate_contracts twice with the requirement "Validate user email address"
    Then both results have the same requirement_hash
    And the requirement_hash is a 16 character string

  Scenario: Different requirements produce different requirement hashes
    Given an LLM client that responds with a valid single-contract JSON payload
    And a ContractArchitect configured with that LLM client
    When I call generate_contracts with requirement "Validate user email address"
    And I call generate_contracts with requirement "Validate user phone number"
    Then the two results have different requirement_hash values

  Scenario: The architect model identifier is echoed back on every result
    Given an LLM client that responds with a valid single-contract JSON payload
    And a ContractArchitect created with model_id "together-llama-3.3-70b"
    When I call generate_contracts with requirement "Summarize a list of orders"
    Then the result's architect_model is "together-llama-3.3-70b"
    And the result's elapsed_seconds is greater than or equal to 0