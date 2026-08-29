Feature: Contract-driven implementation orchestration

  As a caller of the contract orchestration system, I register interface
  contracts, request implementation prompts for them, submit candidate
  code against a contract, and query the resulting status.

  Scenario: Generating an implementation prompt from a contract
    Given a contract with function name "square", signature "(x: int) -> int", and docstring "Return x squared."
    And the contract has a test case named "basic" where input "(4)" should equal expected value "16"
    When I request the implementation prompt for that contract
    Then the prompt contains the line "def square(x: int) -> int:"
    And the prompt contains the docstring "Return x squared."
    And the prompt contains the text "basic: (4) should return 16"
    And the prompt ends with the instruction "Respond with ONLY the function code. No explanations."

  Scenario: Prompt includes hints when the contract provides them
    Given a contract with function name "clamp", signature "(x: int, lo: int, hi: int) -> int", and docstring "Clamp x between lo and hi."
    And the contract has hints "Use min and max" and "Handle lo > hi gracefully"
    When I request the implementation prompt for that contract
    Then the prompt contains a "Hints:" section
    And the prompt lists "Use min and max"
    And the prompt lists "Handle lo > hi gracefully"

  Scenario: Prompt only shows up to three test case examples
    Given a contract with five registered test cases named "case1" through "case5"
    When I request the implementation prompt for that contract
    Then the prompt lists exactly three test case examples
    And the listed examples are "case1", "case2", and "case3"

  Scenario: Requesting a prompt for an unregistered contract fails
    Given no contract has been registered with id "missing_contract"
    When I request the implementation prompt for "missing_contract"
    Then a "ValueError" is raised with message "Contract missing_contract not found"

  Scenario: A newly registered contract is pending
    Given a contract with id "double_number" has just been registered
    And no implementation has been submitted for it
    When I query the status of "double_number"
    Then the status is "pending"

  Scenario: Querying status for an unknown contract fails
    Given no contract has been registered with id "ghost_contract"
    When I query the status of "ghost_contract"
    Then a "ValueError" is raised with message "Contract ghost_contract not found"

  Scenario: Submitting syntactically invalid code fails validation without running it
    Given a contract with id "broken_syntax" is registered
    When I submit the code "def broken(:\n    return" for contract "broken_syntax"
    Then the returned implementation has status "failed"
    And the returned implementation error mentions "Syntax error"

  Scenario: Submitting a correct implementation validates the contract
    Given a contract with id "add_numbers", function name "add", signature "(a: int, b: int) -> int" is registered
    And the contract has a test case named "sum_two" where input "(2, 3)" should equal expected value "5"
    When I submit the code "def add(a: int, b: int) -> int:\n    return a + b" for contract "add_numbers"
    Then the returned implementation has status "validated"
    And the test result for "sum_two" is true
    And querying the status of "add_numbers" now returns "validated"

  Scenario: Submitting an implementation that fails a test case marks the contract as failed
    Given a contract with id "add_numbers", function name "add", signature "(a: int, b: int) -> int" is registered
    And the contract has a test case named "sum_two" where input "(2, 3)" should equal expected value "5"
    When I submit the code "def add(a: int, b: int) -> int:\n    return a - b" for contract "add_numbers"
    Then the returned implementation has status "failed"
    And the test result for "sum_two" is false