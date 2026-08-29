Feature: Polyglot TDD Runner orchestration
  As a caller of PolyglotTDDRunner, I want to run RED→GREEN→REFACTOR cycles
  across one or more languages and get back per-language results plus a
  combined token efficiency report.

  Scenario: Running a single language that reaches GREEN
    Given a PolyglotTDDRunner configured with a pod factory for "python"
    And a feature requirement "the add function returns the sum of two numbers"
    When I call run with languages ["python"], a test file, and an implementation file
    Then the returned PolyglotRunResult contains a language_results entry for "python"
    And that entry's green PhaseResult has passed equal to True
    And the efficiency_report includes a scored entry for "python"

  Scenario: Running multiple languages produces independent results for each
    Given a PolyglotTDDRunner configured with pod factories for "python" and "go"
    And a feature requirement "the multiply function returns the product of two numbers"
    When I call run with languages ["python", "go"], a test file, and an implementation file
    Then the returned PolyglotRunResult contains language_results entries for both "python" and "go"
    And the efficiency_report's scored entries cover both "python" and "go"

  Scenario: A language that never reaches GREEN still completes and does not block other languages
    Given a PolyglotTDDRunner configured with pod factories for "python" and "go"
    And the "go" pod is configured so GREEN never passes within max_cycles
    When I call run with languages ["go", "python"], a test file, and an implementation file
    Then the "go" language_results entry has a green PhaseResult with passed equal to False
    And the "go" language_results entry's refactor PhaseResult has passed equal to False
    And the "python" language_results entry's green PhaseResult has passed equal to True

  Scenario: A redundancy checker skips a test that is equivalent to an existing one
    Given a PolyglotTDDRunner configured with a redundancy_checker that reports a redundant match with confidence 0.92 and reason "duplicate of test_add"
    And a feature requirement "the add function returns the sum of two numbers"
    When I call run with languages ["python"], an existing test file, and an implementation file
    Then the "python" language_results entry has cycles_to_green equal to 0
    And the "python" language_results entry's red, green, and refactor PhaseResults all have passed equal to True
    And the "python" pod_run's token_usage in the efficiency report is empty

  Scenario: Running from a Gherkin feature file parses the spec and executes the same run
    Given a PolyglotTDDRunner configured with a pod factory for "python"
    And a valid Gherkin ".feature" file describing a requirement
    When I call run_from_feature with that feature file path, languages ["python"], a test file, and an implementation file
    Then the returned PolyglotRunResult contains a language_results entry for "python"
    And the language_results entry's feature requirement matches the requirement parsed from the feature file

  Scenario: Requesting an unsupported language raises an error
    Given a PolyglotTDDRunner configured with the default PodFactory
    When I call run with languages ["ruby"], a test file, and an implementation file
    Then a ValueError is raised with message "Unsupported language: ruby"

  Scenario: The combined efficiency report reflects cycles_to_green per language
    Given a PolyglotTDDRunner configured with pod factories for "python" and "typescript"
    And the "python" pod reaches GREEN on its 1st attempt and the "typescript" pod reaches GREEN on its 3rd attempt
    When I call run with languages ["python", "typescript"], a test file, and an implementation file
    Then the "python" language_results entry has cycles_to_green equal to 1
    And the "typescript" language_results entry has cycles_to_green equal to 3