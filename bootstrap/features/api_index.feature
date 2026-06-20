Feature: ACE Enterprise public API index
  As a TypeScript developer installing ace-enterprise-oss
  I want a single import path for the public API
  So that I can use ACE without knowing internal module paths

  Scenario: Import AutonomousTDDAgent from package root
    Given the ace-enterprise-oss package is installed
    When a consumer imports AutonomousTDDAgent from "ace-enterprise-oss"
    Then AutonomousTDDAgent is a class with a buildFeature method
    And buildFeature accepts a requirement string and returns a result with testFiles and implementationFiles

  Scenario: Import ProjectConfig from package root
    Given the ace-enterprise-oss package is installed
    When a consumer imports ProjectConfig from "ace-enterprise-oss"
    Then ProjectConfig is a class with a static load method that accepts a project path string
    And a ProjectConfig instance has fields projectRoot, testDir, srcDir, playbookId, and maxIterations

  Scenario: Import LLMClient from package root
    Given the ace-enterprise-oss package is installed
    When a consumer imports LLMClient from "ace-enterprise-oss"
    Then LLMClient is a class that accepts provider and model as constructor arguments

  Scenario: Import AdaptiveBroker from package root
    Given the ace-enterprise-oss package is installed
    When a consumer imports AdaptiveBroker from "ace-enterprise-oss"
    Then AdaptiveBroker is a class with a routeTask method that accepts a task description

  Scenario: Import PlaybookManager from package root
    Given the ace-enterprise-oss package is installed
    When a consumer imports PlaybookManager from "ace-enterprise-oss"
    Then PlaybookManager is a class with getOrCreatePlaybook and addBullet methods

  Scenario: All core exports resolve from a single destructured import
    Given the ace-enterprise-oss package is installed
    When a consumer writes:
      """
      import { AutonomousTDDAgent, ProjectConfig, LLMClient, AdaptiveBroker, PlaybookManager } from "ace-enterprise-oss"
      """
    Then all five imports resolve without error
    And none of the imported values are undefined

  Scenario: Package exports a VERSION constant
    Given the ace-enterprise-oss package is installed
    When a consumer imports VERSION from "ace-enterprise-oss"
    Then VERSION is a non-empty string in semver format "major.minor.patch"
