Feature: TypeScript code generation for TDD cycles

  As a caller driving a TDD workflow
  I want to generate TypeScript test code, implementation code, and refactored code
  So that I can automate the red-green-refactor cycle for a TypeScript feature

  Background:
    Given a PodSpec with test_file "calculator.test.ts", implementation_file "calculator.ts", and feature_requirement "add two numbers"

  Scenario: Generating a test extracts fenced TypeScript code from the LLM response
    Given an LLM client that returns the content:
      """
      Here is the test:
      import { add } from './calculator';
      describe('add', () => {
        it('adds two numbers', () => {
          expect(add(2, 3)).toBe(5);
        });
      });
      """
    When I call generate_test with the spec and no existing code
    Then the returned code is exactly:
      """
      import { add } from './calculator';
      describe('add', () => {
        it('adds two numbers', () => {
          expect(add(2, 3)).toBe(5);
        });
      });
      """

  Scenario: Generating an implementation extracts code even when the fence is unclosed
    Given an LLM client that returns the content:
      """
      export function add(a: number, b: number): number {
        return a + b;
      }
      """
    When I call generate_implementation with the spec, empty error output, and empty test code
    Then the returned code is exactly:
      """
      export function add(a: number, b: number): number {
        return a + b;
      }
      """

  Scenario: Generating an implementation falls back to stripping a conversational preamble when there is no code fence
    Given an LLM client that returns the content:
      """
      Sure, here is the implementation you asked for.
      export function add(a: number, b: number): number {
        return a + b;
      }
      """
    When I call generate_implementation with the spec, empty error output, and empty test code
    Then the returned code is exactly:
      """
      export function add(a: number, b: number): number {
        return a + b;
      }
      """

  Scenario: Implementation generation escalates to the fallback client after the configured number of attempts
    Given a primary LLM client and a fallback LLM client
    And the worker agent was created with escalate_after set to 2
    When I call generate_implementation with the spec three times in a row
    Then the first 2 calls use the primary LLM client
    And the 3rd call uses the fallback LLM client

  Scenario: Implementation generation never escalates when no fallback client is configured
    Given a primary LLM client only, with no fallback client
    And the worker agent was created with escalate_after set to 2
    When I call generate_implementation with the spec five times in a row
    Then all 5 calls use the primary LLM client

  Scenario: Generating a refactor extracts code from a plain untagged fence
    Given an LLM client that returns the content:
      """
      export function add(a: number, b: number): number {
        return a + b;
      }
      """
    When I call generate_refactor with the spec and current code "export function add(a, b) { return a + b; }"
    Then the returned code is exactly:
      """
      export function add(a: number, b: number): number {
        return a + b;
      }
      """

  Scenario: Generating code with no fence and no recognizable TypeScript syntax returns the trimmed raw content
    Given an LLM client that returns the content:
      """
        I could not complete this request.  
      """
    When I call generate_test with the spec and no existing code
    Then the returned code is exactly "I could not complete this request."