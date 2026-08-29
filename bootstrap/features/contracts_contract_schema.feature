Feature: Contract Schema YAML loading and persistence
  As a caller of the contract schema API
  I want to load, validate, and save interface contract specifications
  So that I can round-trip contract.yml data reliably

  Scenario: Loading a valid contract with a single test case
    Given a YAML string containing a "contracts" list with one entry having id "tax-001", function_name "calculate_tax", signature "(income: float, rate: float) -> float", complexity 1, and one test case named "basic" with input "(1000, 0.2)" and expected "200.0"
    When I load the contracts from the YAML string
    Then I receive a list containing one contract
    And the contract has id "tax-001" and function_name "calculate_tax"
    And the contract has exactly one test case named "basic"

  Scenario: Loading YAML missing the top-level "contracts" key raises an error
    Given a YAML string that does not contain a "contracts" key
    When I attempt to load the contracts from the YAML string
    Then a ValueError is raised

  Scenario: Loading a contract entry missing function_name raises an error
    Given a YAML string with a contracts entry that has no "function_name" field
    When I attempt to load the contracts from the YAML string
    Then a ValueError is raised

  Scenario: Loading a contract entry with no test cases raises an error
    Given a YAML string with a contracts entry that has an empty "test_cases" list
    When I attempt to load the contracts from the YAML string
    Then a ValueError is raised

  Scenario: Loading a contract entry with an out-of-range complexity raises an error
    Given a YAML string with a contracts entry having complexity 7
    When I attempt to load the contracts from the YAML string
    Then a ValueError is raised

  Scenario: Loading a contract entry that omits optional fields uses defaults
    Given a YAML string with a contracts entry that omits "signature", "docstring", "hints", and "fixtures", but includes "id", "function_name", and one test case
    When I load the contracts from the YAML string
    Then the resulting contract has signature "()" and docstring "" and an empty hints list

  Scenario: Loading contracts from a file delegates to string loading
    Given a file path pointing to a valid contract.yml file with one contract entry
    When I load the contracts from that file
    Then I receive a list containing one contract matching the file's content

  Scenario: Saving contracts to a file writes YAML that can be loaded back
    Given a list containing one ContractSpec with id "tax-001", function_name "calculate_tax", signature "(income: float, rate: float) -> float", complexity 1, and one test case named "basic"
    When I save the contracts to a file path and then load contracts from that same file
    Then the loaded list contains one contract with id "tax-001" and function_name "calculate_tax"