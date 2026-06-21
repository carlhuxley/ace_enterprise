Feature: Contract Schema YAML Loading and Saving

  Scenario: Load a valid contract from YAML string
    Given a YAML string with a single contract
      """
      contracts:
        - id: tax-001
          function_name: calculate_tax
          signature: "(income: float, rate: float) -> float"
          docstring: "Calculate tax amount"
          complexity: 1
          test_cases:
            - name: basic
              input: "(1000, 0.2)"
              expected: "200.0"
          hints:
            - "Simple multiplication"
      """
    When load_contracts is called with the YAML string
    Then a list containing 1 ContractSpec is returned
    And the ContractSpec has id "tax-001"
    And the ContractSpec has function_name "calculate_tax"
    And the ContractSpec has signature "(income: float, rate: float) -> float"
    And the ContractSpec has docstring "Calculate tax amount"
    And the ContractSpec has complexity 1
    And the ContractSpec has 1 test case
    And the first test case has name "basic"
    And the first test case has input "(1000, 0.2)"
    And the first test case has expected "200.0"
    And the ContractSpec has 1 hint "Simple multiplication"

  Scenario: Load contract with minimal required fields
    Given a YAML string with minimal contract fields
      """
      contracts:
        - id: simple-001
          function_name: add_numbers
          test_cases:
            - name: test1
              input: "(2, 3)"
              expected: "5"
      """
    When load_contracts is called with the YAML string
    Then a list containing 1 ContractSpec is returned
    And the ContractSpec has signature "()"
    And the ContractSpec has docstring ""
    And the ContractSpec has complexity 1
    And the ContractSpec has 0 hints

  Scenario: Load multiple contracts from YAML string
    Given a YAML string with three contracts
      """
      contracts:
        - id: func-001
          function_name: func_one
          test_cases:
            - name: test1
              input: "(1,)"
              expected: "1"
        - id: func-002
          function_name: func_two
          test_cases:
            - name: test2
              input: "(2,)"
              expected: "2"
        - id: func-003
          function_name: func_three
          test_cases:
            - name: test3
              input: "(3,)"
              expected: "3"
      """
    When load_contracts is called with the YAML string
    Then a list containing 3 ContractSpec objects is returned
    And the first ContractSpec has id "func-001"
    And the second ContractSpec has id "func-002"
    And the third ContractSpec has id "func-003"

  Scenario: Load contract with fixtures
    Given a YAML string with a contract containing fixtures
      """
      contracts:
        - id: db-001
          function_name: query_db
          test_cases:
            - name: query_test
              input: "('SELECT * FROM users',)"
              expected: "[]"
          fixtures:
            setup: "db.connect()"
            teardown: "db.close()"
      """
    When load_contracts is called with the YAML string
    Then a list containing 1 ContractSpec is returned
    And the ContractSpec has fixtures with setup "db.connect()"
    And the ContractSpec has fixtures with teardown "db.close()"

  Scenario: Reject YAML without contracts key
    Given a YAML string without contracts key
      """
      data:
        - id: invalid
      """
    When load_contracts is called with the YAML string
    Then a ValueError is raised with message "YAML must contain 'contracts' key"

  Scenario: Reject contract without function_name
    Given a YAML string with a contract missing function_name
      """
      contracts:
        - id: bad-001
          test_cases:
            - name: test1
              input: "()"
              expected: "None"
      """
    When load_contracts is called with the YAML string
    Then a ValueError is raised with message "Contract bad-001 missing function_name"

  Scenario: Reject contract without test_cases
    Given a YAML string with a contract missing test_cases
      """
      contracts:
        - id: bad-002
          function_name: no_tests
      """
    When load_contracts is called with the YAML string
    Then a ValueError is raised with message "Contract bad-002 must have at least one test case"

  Scenario: Reject contract with invalid complexity
    Given a YAML string with complexity 7
      """
      contracts:
        - id: bad-003
          function_name: too_complex
          complexity: 7
          test_cases:
            - name: test1
              input: "()"
              expected: "None"
      """
    When load_contracts is called with the YAML string
    Then a ValueError is raised with message "Contract bad-003 complexity must be 1-6, got 7"

  Scenario: Save contracts to YAML file
    Given a ContractSpec with id "save-001", function_name "save_func", complexity 2, and one test case
    When save_contracts is called with the ContractSpec list and a file path
    Then the file is written with valid YAML
    And the YAML contains a contracts key with 1 entry
    And the entry has id "save-001"
    And the entry has function_name "save_func"
    And the entry has complexity 2

  Scenario: Convert ContractSpec to InterfaceContract
    Given a ContractSpec with id "convert-001", function_name "convert_func", and test cases
    When to_interface_contract is called on the ContractSpec
    Then an InterfaceContract is returned
    And the InterfaceContract has contract_id "convert-001"
    And the InterfaceContract has function_name "convert_func"
    And the InterfaceContract test_cases match the ContractSpec test_cases