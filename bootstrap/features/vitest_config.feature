Feature: Vitest configuration for ace-enterprise-oss
  As a developer running the ace-enterprise-oss test suite
  I want vitest configured with globals enabled
  So that describe, it, expect and other test helpers are available without explicit imports

  Scenario: describe is available globally without import
    Given a test file that uses describe without importing it from vitest
    When vitest runs the test file
    Then describe is defined and callable

  Scenario: it and test are available globally without import
    Given a test file that uses it and test without importing them from vitest
    When vitest runs the test file
    Then it and test are defined and callable

  Scenario: expect is available globally without import
    Given a test file that uses expect without importing it from vitest
    When vitest runs the test file
    Then expect is defined and callable

  Scenario: beforeEach and afterEach are available globally without import
    Given a test file that uses beforeEach and afterEach without importing them from vitest
    When vitest runs the test file
    Then beforeEach and afterEach are defined and callable

  Scenario: test environment is node
    Given the vitest configuration
    When the test environment is inspected
    Then the environment is "node"

  Scenario: config exports a valid vitest defineConfig object
    Given the vitest.config.ts file
    When the default export is inspected
    Then it is a valid vitest configuration object produced by defineConfig
    And it has a test property with globals set to true
    And it has a test property with environment set to "node"
