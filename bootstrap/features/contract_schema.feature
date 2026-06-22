Feature: Contract Schema YAML Loading and Saving

  Scenario: Load a valid contract from YAML string
    Given a YAML string with a single contract
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
    When loadContracts is called with the YAML string
    Then a list containing 1 ContractSpec is returned
    And the ContractSpec has id "tax-001"
    And the ContractSpec has functionName "calculateTax"
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
          functionName: addNumbers
          testCases:
            - name: test1
              input: "(2, 3)"
              expected: "5"
      """
    When loadContracts is called with the YAML string
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
          functionName: funcOne
          testCases:
            - name: test1
              input: "(1,)"
              expected: "1"
        - id: func-002
          functionName: funcTwo
          testCases:
            - name: test2
              input: "(2,)"
              expected: "2"
        - id: func-003
          functionName: funcThree
          testCases:
            - name: test3
              input: "(3,)"
              expected: "3"
      """
    When loadContracts is called with the YAML string
    Then a list containing 3 ContractSpec objects is returned
    And the first ContractSpec has id "func-001"
    And the second ContractSpec has id "func-002"
    And the third ContractSpec has id "func-003"

  Scenario: Load contract with fixtures
    Given a YAML string with a contract containing fixtures
      """
      contracts:
        - id: db-001
          functionName: queryDb
          testCases:
            - name: queryTest
              input: "('SELECT * FROM users',)"
              expected: "[]"
          fixtures:
            setup: "db.connect()"
            teardown: "db.close()"
      """
    When loadContracts is called with the YAML string
    Then a list containing 1 ContractSpec is returned
    And the ContractSpec has fixtures with setup "db.connect()"
    And the ContractSpec has fixtures with teardown "db.close()"

  Scenario: Reject YAML without contracts key
    Given a YAML string without contracts key
      """
      data:
        - id: invalid
      """
    When loadContracts is called with the YAML string
    Then a ValueError is raised with message "YAML must contain 'contracts' key"

  Scenario: Reject contract without functionName
    Given a YAML string with a contract missing functionName
      """
      contracts:
        - id: bad-001
          testCases:
            - name: test1
              input: "()"
              expected: "None"
      """
    When loadContracts is called with the YAML string
    Then a ValueError is raised with message "missing functionName"

  Scenario: Reject contract without testCases
    Given a YAML string with a contract missing testCases
      """
      contracts:
        - id: bad-002
          functionName: noTests
      """
    When loadContracts is called with the YAML string
    Then a ValueError is raised with message "must have at least one test case"

  Scenario: Reject contract with invalid complexity
    Given a YAML string with complexity 7
      """
      contracts:
        - id: bad-003
          functionName: tooComplex
          complexity: 7
          testCases:
            - name: test1
              input: "()"
              expected: "None"
      """
    When loadContracts is called with the YAML string
    Then a ValueError is raised with message "complexity must be 1-6, got 7"

  Scenario: Save contracts to YAML file
    Given a ContractSpec with id "save-001", functionName "saveFunc", complexity 2, and one test case
    When saveContracts is called with the ContractSpec list and a file path
    Then the file is written with valid YAML
    And the YAML contains a contracts key with 1 entry
    And the entry has id "save-001"
    And the entry has functionName "saveFunc"
    And the entry has complexity 2

  Scenario: Convert ContractSpec to InterfaceContract
    Given a ContractSpec with id "convert-001", functionName "convertFunc", and test cases
    When toInterfaceContract is called on the ContractSpec
    Then an InterfaceContract is returned
    And the InterfaceContract has contractId "convert-001"
    And the InterfaceContract has functionName "convertFunc"
    And the InterfaceContract testCases match the ContractSpec testCases
