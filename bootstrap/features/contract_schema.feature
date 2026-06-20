Feature: Contract Schema YAML Loading and Saving

  Scenario: Load a valid contract from YAML string
    Given a YAML string with a single contract:
      """
      contracts:
        - id: tax-001
          functionName: calculateTax
          signature: "(income: float, rate: float) -> float"
          docstring: "Calculate tax amount"
          complexity: 1
          testCases:
            - name: basic
              input: "(1000, 0.2)"
              expected: "200.0"
          hints:
            - "Simple multiplication"
      """
    When I call loadContracts with the YAML string
    Then I receive a list containing 1 ContractSpec
    And the ContractSpec has id "tax-001"
    And the ContractSpec has functionName "calculate_tax"
    And the ContractSpec has signature "(income: float, rate: float) -> float"
    And the ContractSpec has docstring "Calculate tax amount"
    And the ContractSpec has complexity 1
    And the ContractSpec has 1 test case
    And the first test case has name "basic"
    And the first test case has input "(1000, 0.2)"
    And the first test case has expected "200.0"
    And the ContractSpec has 1 hint "Simple multiplication"

  Scenario: Load contract with minimal required fields
    Given a YAML string with minimal contract fields:
      """
      contracts:
        - id: min-001
          functionName: simpleFunc
          testCases:
            - name: test1
              input: "()"
              expected: "42"
      """
    When I call loadContracts with the YAML string
    Then I receive a list containing 1 ContractSpec
    And the ContractSpec has id "min-001"
    And the ContractSpec has functionName "simple_func"
    And the ContractSpec has signature "()"
    And the ContractSpec has docstring ""
    And the ContractSpec has complexity 1
    And the ContractSpec has 0 hints

  Scenario: Load contract with fixtures
    Given a YAML string with fixtures:
      """
      contracts:
        - id: fixture-001
          functionName: dbQuery
          testCases:
            - name: queryTest
              input: "('SELECT * FROM users',)"
              expected: "[]"
          fixtures:
            setup: "db.connect()"
            teardown: "db.close()"
      """
    When I call loadContracts with the YAML string
    Then I receive a list containing 1 ContractSpec
    And the ContractSpec has fixtures with setup "db.connect()"
    And the ContractSpec has fixtures with teardown "db.close()"

  Scenario: Load multiple contracts from YAML
    Given a YAML string with 3 contracts:
      """
      contracts:
        - id: contract-1
          functionName: func1
          testCases:
            - name: test1
              input: "(1,)"
              expected: "2"
        - id: contract-2
          functionName: func2
          testCases:
            - name: test2
              input: "(3,)"
              expected: "6"
        - id: contract-3
          functionName: func3
          testCases:
            - name: test3
              input: "(5,)"
              expected: "10"
      """
    When I call loadContracts with the YAML string
    Then I receive a list containing 3 ContractSpec objects

  Scenario: Reject YAML without contracts key
    Given a YAML string without contracts key:
      """
      otherData:
        - id: invalid
      """
    When I call loadContracts with the YAML string
    Then a ValueError is raised with message "YAML must contain 'contracts' key"

  Scenario: Reject contract without functionName
    Given a YAML string with contract missing functionName:
      """
      contracts:
        - id: bad-001
          testCases:
            - name: test1
              input: "()"
              expected: "1"
      """
    When I call loadContracts with the YAML string
    Then a ValueError is raised with message containing "missing function_name"

  Scenario: Reject contract without test cases
    Given a YAML string with contract missing testCases:
      """
      contracts:
        - id: no-tests
          functionName: myFunc
      """
    When I call loadContracts with the YAML string
    Then a ValueError is raised with message containing "must have at least one test case"

  Scenario: Reject contract with invalid complexity
    Given a YAML string with complexity 7:
      """
      contracts:
        - id: complex-001
          functionName: hardFunc
          complexity: 7
          testCases:
            - name: test1
              input: "()"
              expected: "1"
      """
    When I call loadContracts with the YAML string
    Then a ValueError is raised with message containing "complexity must be 1-6"

  Scenario: Save contracts to YAML file
    Given a ContractSpec with id "save-001", functionName "save_func", complexity 2, and one test case
    When I call saveContracts with the ContractSpec list and a file path
    Then the file is written with valid YAML
    And the YAML contains a contracts key with 1 entry
    And the entry has id "save-001"
    And the entry has functionName "save_func"
    And the entry has complexity 2

  Scenario: Convert ContractSpec to InterfaceContract
    Given a ContractSpec with id "convert-001", functionName "convert_func", and test cases
    When I call toInterfaceContract on the ContractSpec
    Then I receive an InterfaceContract object
    And the InterfaceContract has contractId "convert-001"
    And the InterfaceContract has functionName "convert_func"
    And the InterfaceContract has TestCase objects matching the original test cases