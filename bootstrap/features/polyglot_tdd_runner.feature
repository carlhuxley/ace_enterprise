Feature: Polyglot TDD Runner
  As a polyglot TDD orchestrator
  I want to run RED-GREEN-REFACTOR cycles across multiple languages
  So that I can compare token efficiency and behavior across language implementations

  Scenario: Run TDD cycle for a single language with immediate green
    Given a pod factory that creates language pods
    And a PolyglotTDDRunner with max_cycles set to 5
    And a feature requirement "Implement fizzbuzz function"
    And a test file path "test_fizzbuzz.py"
    And an implementation file path "fizzbuzz.py"
    And a language list containing "python"
    And the python pod returns passed=True for RED phase with output "Test written"
    And the python pod returns passed=True for GREEN phase on cycle 1 with output "Tests pass"
    And the python pod returns passed=True for REFACTOR phase with output "Code refactored"
    And the python pod reports token_usage of 1500
    When I call run with the feature requirement, test file, implementation file, and languages
    Then the PolyglotRunResult contains 1 language result
    And the language result for "python" has cycles_to_green equal to 1
    And the language result for "python" has red.passed equal to True
    And the language result for "python" has green.passed equal to True
    And the language result for "python" has refactor.passed equal to True
    And the efficiency_report contains 1 pod run

  Scenario: Run TDD cycle requiring multiple green attempts before passing
    Given a pod factory that creates language pods
    And a PolyglotTDDRunner with max_cycles set to 5
    And a feature requirement "Implement calculator"
    And a test file path "test_calc.go"
    And an implementation file path "calc.go"
    And a language list containing "go"
    And the go pod returns passed=True for RED phase
    And the go pod returns passed=False for GREEN phase on cycle 1
    And the go pod returns passed=False for GREEN phase on cycle 2
    And the go pod returns passed=True for GREEN phase on cycle 3
    And the go pod returns passed=True for REFACTOR phase
    And the go pod reports token_usage of 3200
    When I call run with the feature requirement, test file, implementation file, and languages
    Then the language result for "go" has cycles_to_green equal to 3
    And the language result for "go" has green.passed equal to True

  Scenario: Run TDD cycle that never reaches green within max cycles
    Given a pod factory that creates language pods
    And a PolyglotTDDRunner with max_cycles set to 3
    And a feature requirement "Complex algorithm"
    And a test file path "test_algo.py"
    And an implementation file path "algo.py"
    And a language list containing "python"
    And the python pod returns passed=True for RED phase
    And the python pod returns passed=False for GREEN phase on all cycles
    And the python pod returns passed=True for REFACTOR phase
    And the python pod reports token_usage of 5000
    When I call run with the feature requirement, test file, implementation file, and languages
    Then the language result for "python" has cycles_to_green equal to 3
    And the language result for "python" has green.passed equal to False
    And the language result for "python" has refactor.passed equal to True
    And the efficiency_report contains 1 pod run

  Scenario: Run TDD cycles for multiple languages simultaneously
    Given a pod factory that creates language pods
    And a PolyglotTDDRunner with max_cycles set to 5
    And a feature requirement "String reverser"
    And a test file path "test_reverse.txt"
    And an implementation file path "reverse.txt"
    And a language list containing "python" and "go"
    And the python pod returns passed=True for all phases on cycle 1
    And the python pod reports token_usage of 1200
    And the go pod returns passed=True for RED phase
    And the go pod returns passed=False for GREEN phase on cycle 1
    And the go pod returns passed=True for GREEN phase on cycle 2
    And the go pod returns passed=True for REFACTOR phase
    And the go pod reports token_usage of 2400
    When I call run with the feature requirement, test file, implementation file, and languages
    Then the PolyglotRunResult contains 2 language results
    And the language result for "python" has cycles_to_green equal to 1
    And the language result for "go" has cycles_to_green equal to 2
    And the efficiency_report contains 2 pod runs

  Scenario: Run from feature file parses Gherkin and executes TDD cycle
    Given a pod factory that creates language pods
    And a PolyglotTDDRunner with max_cycles set to 5
    And a feature file at path "features/calculator.feature"
    And a test file path "test_calc.py"
    And an implementation file path "calc.py"
    And a language list containing "python"
    And the feature file parses to requirement "Add two numbers"
    And the python pod returns passed=True for all phases on cycle 1
    And the python pod reports token_usage of 800
    When I call run_from_feature with the feature path, languages, test file, and implementation file
    Then the PolyglotRunResult contains 1 language result
    And the language result for "python" has cycles_to_green equal to 1

  Scenario: Unsupported language raises error during pod creation
    Given a pod factory that creates language pods
    And a PolyglotTDDRunner with max_cycles set to 5
    And a feature requirement "Test feature"
    And a test file path "test.txt"
    And an implementation file path "impl.txt"
    And a language list containing "rust"
    When I call run with the feature requirement, test file, implementation file, and languages
    Then a ValueError is raised with message "Unsupported language: rust"

  Scenario: Custom token efficiency reporter is used when provided
    Given a custom token efficiency reporter
    And a pod factory that creates language pods
    And a PolyglotTDDRunner with max_cycles set to 5 and the custom reporter
    And a feature requirement "Simple function"
    And a test file path "test.py"
    And an implementation file path "impl.py"
    And a language list containing "python"
    And the python pod returns passed=True for all phases on cycle 1
    And the python pod reports token_usage of 1000
    When I call run with the feature requirement, test file, implementation file, and languages
    Then the custom reporter's score method was called with 1 pod run
    And the efficiency_report is the result from the custom reporter