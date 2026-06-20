Feature: Iterative TDD Runner
  As a test automation system
  I want to run multiple TDD cycles iteratively
  So that I can implement features incrementally using RED-GREEN-REFACTOR

  Scenario: Successful planner-driven execution completes before max iterations
    Given an IterativeTDDRunner with max_iterations set to 10
    And an IncrementalPlanner that returns COMPLETE after 3 cycles
    And each TDD cycle succeeds with red failing then green passing
    When I call run with requirement "implement calculator"
    Then the IterativeResult has complete set to True
    And the IterativeResult has iterations set to 3
    And the IterativeResult has 3 cycles
    And the IterativeResult success property returns True

  Scenario: Planner-driven execution hits max iterations without completion
    Given an IterativeTDDRunner with max_iterations set to 5
    And an IncrementalPlanner that never returns COMPLETE
    And each TDD cycle succeeds
    When I call run with requirement "implement complex feature"
    Then the IterativeResult has complete set to False
    And the IterativeResult has iterations set to 5
    And the IterativeResult has 5 cycles
    And the IterativeResult success property returns False

  Scenario: Gherkin-driven execution processes all scenarios in order
    Given an IterativeTDDRunner with max_iterations set to 10
    And a list of 4 gherkin_scenarios
    And each TDD cycle succeeds
    When I call run with requirement "feature spec" and gherkin_scenarios provided
    Then the IterativeResult has complete set to True
    And the IterativeResult has iterations set to 4
    And the IterativeResult has 4 cycles
    And each cycle corresponds to one scenario in declaration order

  Scenario: Gherkin-driven execution from feature file uses file stem for paths
    Given an IterativeTDDRunner
    And a feature file at path "features/shopping_cart.feature" with 2 scenarios
    When I call run_from_feature with "features/shopping_cart.feature"
    Then all cycles use test_file "test_shopping_cart.py"
    And all cycles use impl_file "shopping_cart.py"
    And the IterativeResult has 2 cycles

  Scenario: Failed cycle marks result as incomplete
    Given an IterativeTDDRunner with max_iterations set to 10
    And an IncrementalPlanner that returns COMPLETE after 3 cycles
    And cycle 2 fails with green not passing
    When I call run with requirement "implement feature"
    Then the IterativeResult has complete set to True
    And the IterativeResult has 3 cycles
    And the IterativeResult success property returns False

  Scenario: Planner parse error skips cycle and continues
    Given an IterativeTDDRunner with max_iterations set to 5
    And an IncrementalPlanner that returns None on cycle 2
    And an IncrementalPlanner that returns COMPLETE after cycle 4
    And other cycles succeed
    When I call run with requirement "implement feature"
    Then the IterativeResult has complete set to True
    And the IterativeResult has 3 cycles
    And cycle 2 was skipped due to parse error

  Scenario: IterativeResult success requires both complete and all cycles successful
    Given an IterativeResult with complete set to True
    And 3 cycles where all have success True
    Then the success property returns True
    Given an IterativeResult with complete set to False
    And 3 cycles where all have success True
    Then the success property returns False
    Given an IterativeResult with complete set to True
    And 3 cycles where cycle 2 has success False
    Then the success property returns False