Feature: Iterative TDD Runner
  As a caller driving automated test-driven development
  I want to run RED-GREEN-REFACTOR cycles either from Gherkin scenarios or from a free-form requirement
  So that I get a session result describing what was built and whether it succeeded

  Scenario: Running with Gherkin scenarios completes one cycle per scenario
    Given a requirement "Implement a stack with push and pop"
    And a list of 3 Gherkin scenarios
    When I call run with the requirement and the Gherkin scenarios
    Then the result contains 3 cycles
    And the result's iterations equals 3

  Scenario: All Gherkin scenarios succeeding marks the session complete and successful
    Given a requirement and a list of 2 Gherkin scenarios
    And every scenario cycle succeeds
    When I call run with the requirement and the Gherkin scenarios
    Then the result's complete flag is True
    And the result's success property is True

  Scenario: A failing Gherkin scenario cycle leaves the session incomplete
    Given a requirement and a list of 2 Gherkin scenarios
    And the second scenario's cycle fails
    When I call run with the requirement and the Gherkin scenarios
    Then the result's success property is False

  Scenario: Running with a plain requirement string uses planner-driven mode until COMPLETE
    Given a requirement "Implement a calculator that adds two numbers"
    And no Gherkin scenarios are supplied
    And the planner signals COMPLETE after 4 cycles
    When I call run with only the requirement
    Then the result contains 4 cycles
    And the result's complete flag is True
    And the result's iterations equals 4

  Scenario: Planner-driven mode stops at max_iterations if never told COMPLETE
    Given a requirement string and no Gherkin scenarios
    And the runner was created with max_iterations 5
    And the planner never returns COMPLETE
    When I call run with only the requirement
    Then the result's complete flag is False
    And the result's iterations equals 5

  Scenario: Running from a .feature file parses scenarios and derives file paths from the file name
    Given a Gherkin feature file at "features/shopping_cart.feature"
    When I call run_from_feature with that file path
    Then the runner reads the requirement and scenarios from the parsed feature
    And the resulting test and implementation files are named after "shopping_cart"

  Scenario: A successful iterative session reports overall success
    Given a completed run where every cycle succeeded
    When I check the result's success property
    Then it returns True

  Scenario: An incomplete iterative session never reports overall success
    Given a run that did not finish (complete is False)
    When I check the result's success property
    Then it returns False