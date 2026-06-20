Feature: TypeScript Worker Agent Code Generation

  Scenario: Generate a new test when no existing tests are present
    Given a PodSpec with feature requirement "calculate sum of two numbers"
    And the PodSpec test file is named "calculator.test.ts"
    And the PodSpec implementation file is named "calculator.ts"
    And no existing test code is provided
    When generate_test is called with the PodSpec
    Then the returned code contains TypeScript test syntax
    And the returned code does not contain import statements for vitest globals

  Scenario: Generate a test with existing tests preserved
    Given a PodSpec with feature requirement "multiply two numbers"
    And the PodSpec test file is named "math.test.ts"
    And the PodSpec implementation file is named "math.ts"
    And existing test code contains "describe('add', () => { it('adds 1+1', () => { expect(add(1,1)).toBe(2); }); });"
    When generate_test is called with the PodSpec and existing code
    Then the returned code contains the existing test code
    And the returned code contains additional test code

  Scenario: Generate a test with Gherkin context included
    Given a PodSpec with feature requirement "validate email format"
    And the PodSpec has gherkin_context "Scenario: Valid email\n  Given an email 'user@example.com'\n  Then it should be valid"
    And the PodSpec test file is named "validator.test.ts"
    And the PodSpec implementation file is named "validator.ts"
    When generate_test is called with the PodSpec
    Then the returned code is valid TypeScript

  Scenario: Generate implementation on first attempt uses primary client
    Given a PodSpec with test file name "calc.test.ts"
    And a TypeScriptWorkerAgent with escalate_after set to 2
    And test_code is "it('adds numbers', () => { expect(add(2,3)).toBe(5); });"
    When generate_implementation is called for the first time with the PodSpec
    Then the primary llm_client is used
    And the implementation attempt counter for "calc.test.ts" is incremented to 1

  Scenario: Generate implementation escalates to fallback client after threshold
    Given a PodSpec with test file name "calc.test.ts"
    And a TypeScriptWorkerAgent with escalate_after set to 2
    And a fallback_client is configured
    And generate_implementation has been called 2 times for "calc.test.ts"
    When generate_implementation is called for the third time with the PodSpec
    Then the fallback_client is used instead of the primary client

  Scenario: Generate implementation with error output truncates long errors
    Given a PodSpec with test file name "parser.test.ts"
    And error_output is a string of 4000 characters
    And test_code is "it('parses input', () => { expect(parse('x')).toBeDefined(); });"
    When generate_implementation is called with the PodSpec and error_output
    Then the returned code is extracted from the LLM response

  Scenario: Generate refactor produces TypeScript code
    Given a PodSpec with feature requirement "optimize sorting algorithm"
    And the PodSpec implementation file is named "sort.ts"
    And current_code is "export function sort(arr: number[]): number[] { return arr.sort(); }"
    When generate_refactor is called with the PodSpec and current_code
    Then the returned code is valid TypeScript

  Scenario: Extract code from markdown fenced block
    Given LLM response content is "```typescript\nexport function foo(): void {}\n```"
    When the response is processed by generate_test
    Then the returned code is "export function foo(): void {}"

  Scenario: Extract code from response without fences
    Given LLM response content is "export function bar(): number { return 42; }"
    When the response is processed by generate_implementation
    Then the returned code is "export function bar(): number { return 42; }"