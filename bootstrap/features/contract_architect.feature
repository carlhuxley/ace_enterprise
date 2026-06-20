Feature: Contract Architect - Generate Function Contracts from Requirements

  Scenario: Generate contracts for a simple requirement
    Given an LLM client that returns a valid contract JSON response
    And a ContractArchitect initialized with the LLM client and modelId "test-model"
    When generateContracts is called with requirement "Create a function to add two numbers"
    Then the result success flag is True
    And the result contains 1 or more contracts
    And the result architectModel is "test-model"
    And the result requirementHash is a 16-character hexadecimal string
    And the result elapsedSeconds is greater than 0
    And the result error is None

  Scenario: Generate contracts with multiple functions
    Given an LLM client that returns JSON with 3 contracts
    And a ContractArchitect initialized with the LLM client
    When generateContracts is called with requirement "Build a calculator with add, subtract, and multiply"
    Then the result success flag is True
    And the result contains 3 contracts
    And each contract has an id, functionName, signature, docstring, and complexity
    And each contract has a list of testCases

  Scenario: Generate contracts with fixtures for stateful functions
    Given an LLM client that returns a contract with fixtures
    And a ContractArchitect initialized with the LLM client
    When generateContracts is called with requirement "Create an inventory system with get_total_value function"
    Then the result success flag is True
    And at least one contract has fixtures with setup and teardown code

  Scenario: Handle LLM response with markdown-wrapped JSON
    Given an LLM client that returns JSON wrapped in ```json markdown blocks
    And a ContractArchitect initialized with the LLM client
    When generateContracts is called with requirement "Create a greeting function"
    Then the result success flag is True
    And the contracts are successfully parsed from the markdown-wrapped response

  Scenario: Emit audit events when audit client is provided
    Given an LLM client that returns a contract JSON with 2 contracts
    And an audit client that tracks emitted events
    And a ContractArchitect initialized with both clients and modelId "architect-model"
    When generateContracts is called with requirement "Create helper functions" and sessionId "session-123"
    Then 2 CONTRACT_GENERATED audit events are emitted with actorId "architect-model"
    And each CONTRACT_GENERATED event includes contractId, functionName, complexity, testCaseCount, requirementHash, hasFixtures, and hintCount
    And 1 CONTRACT_DECOMPOSED audit event is emitted with actorId "architect-model"
    And the CONTRACT_DECOMPOSED event includes requirementHash, contractCount of 2, complexityDistribution, avgComplexity, and maxComplexity
    And all audit events have sessionId "session-123"

  Scenario: Handle contract generation failure gracefully
    Given an LLM client that raises an exception "LLM service unavailable"
    And a ContractArchitect initialized with the LLM client and modelId "test-model"
    When generateContracts is called with requirement "Create a function"
    Then the result success flag is False
    And the result contracts list is empty
    And the result error is "LLM service unavailable"
    And the result elapsedSeconds is greater than 0
    And the result requirementHash is a 16-character hexadecimal string

  Scenario: Create architect from configuration
    Given provider "openai", model "gpt-4", baseUrl "https://api.example.com"
    And auditDbUrl ".local/test_audit.db" with enableAudit True
    When createArchitectFromConfig is called with these parameters
    Then a ContractArchitect instance is returned
    And the architect has modelId "openai-gpt-4"
    And the architect has an audit client configured

  Scenario: Create architect with audit disabled via environment
    Given provider "anthropic", model "claude-3"
    And environment variable AUDIT_DISABLED is set to "true"
    When createArchitectFromConfig is called with enableAudit True
    Then a ContractArchitect instance is returned
    And the architect has no audit client configured