Feature: TypeScript Language Pod TDD Cycle Execution

  Scenario: Run red phase with Python-style test file path converts to TypeScript convention
    Given a PodSpec with test_file "test_calculator.py" and implementation_file "calculator.py"
    And the worker agent generates test code "describe('add', () => { it('adds numbers', () => {}); });"
    And the orchestrator pulse returns a PhaseResult with passed false
    When run_red is called with the PodSpec
    Then the test file path is normalized to "calculator.test.ts"
    And the implementation file path is normalized to "calculator.ts"
    And the test code is committed to disk at "calculator.test.ts"
    And a PhaseResult with passed false is returned

  Scenario: Run red phase with existing test file merges with generated code
    Given a PodSpec with test_file "math.test.ts" and implementation_file "math.ts" and cycle_number 1
    And the test file "math.test.ts" exists with content "describe('old', () => {});"
    And the worker agent receives existing_code "describe('old', () => {});" and generates "describe('new', () => {});"
    And the orchestrator pulse returns passed false with output "FAIL" and error "Expected 2 to equal 3"
    When run_red is called with the PodSpec
    Then a PhaseResult with passed false and error "Expected 2 to equal 3" is returned
    And token_usage contains one entry with cycle_number 1

  Scenario: Run red phase catches worker agent exception
    Given a PodSpec with test_file "broken.test.ts" and implementation_file "broken.ts" and cycle_number 2
    And the worker agent raises an exception "LLM timeout"
    When run_red is called with the PodSpec
    Then a PhaseResult with passed false and error "LLM timeout" is returned
    And token_usage contains one entry with cycle_number 2

  Scenario: Run green phase generates implementation and commits on success
    Given a PodSpec with test_file "utils.test.ts" and implementation_file "utils.ts" and cycle_number 3
    And the test file exists with content "describe('utils', () => {});"
    And spec.error_output is "ReferenceError: add is not defined"
    And the worker agent generates implementation "export function add(a, b) { return a + b; }"
    And the orchestrator pulse returns passed true with output "1 passed"
    When run_green is called with the PodSpec
    Then the implementation code is committed to disk at "utils.ts"
    And a PhaseResult with passed true is returned

  Scenario: Run green phase does not commit implementation when tests fail
    Given a PodSpec with test_file "logic.test.ts" and implementation_file "logic.ts" and cycle_number 4
    And the test file exists with content "describe('logic', () => {});"
    And the worker agent generates implementation "export function broken() { return null; }"
    And the orchestrator pulse returns passed false with output "FAIL"
    When run_green is called with the PodSpec
    Then the implementation code is not committed to disk
    And a PhaseResult with passed false is returned

  Scenario: Run refactor phase executes tests without modifying files
    Given a PodSpec with test_file "service.test.ts" and implementation_file "service.ts" and cycle_number 5
    And the test file exists with content "describe('service', () => {});"
    And the implementation file exists with content "export class Service {}"
    And the orchestrator pulse returns passed true with output "All tests passed"
    When run_refactor is called with the PodSpec
    Then a PhaseResult with passed true is returned
    And no files are committed to disk
    And token_usage contains one entry with cycle_number 5

  Scenario: Security breach during orchestrator pulse returns error result
    Given a PodSpec with test_file "malicious.test.ts" and implementation_file "malicious.ts" and cycle_number 6
    And the worker agent generates test code "import('fs').then(fs => fs.readFileSync('/etc/passwd'));"
    And the orchestrator pulse raises SecurityBreachError "Attempted file system access"
    When run_red is called with the PodSpec
    Then a PhaseResult with passed false and error "SecurityBreach: Attempted file system access" is returned
    And token_usage contains one entry with cycle_number 6

  Scenario: Token usage tracking accumulates across multiple phases
    Given a PodSpec with cycle_number 7
    And the worker agent LLM client returns prompt_tokens 150 and completion_tokens 80
    When run_red is called with the PodSpec
    And the worker agent LLM client returns prompt_tokens 200 and completion_tokens 120
    And run_green is called with the PodSpec
    Then token_usage contains two entries
    And the first entry has cycle_number 7 with input_tokens 150 and output_tokens 80
    And the second entry has cycle_number 7 with input_tokens 200 and output_tokens 120