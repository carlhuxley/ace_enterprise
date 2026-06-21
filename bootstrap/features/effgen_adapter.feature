Feature: EffGen Adapter

  Scenario: Register a single effGen agent with capabilities
    Given a capability registry
    And an EffGenAdapter initialized with the registry
    When I register an agent with agentRef "agent-1", endpoint "http://localhost:8000", modelName "Qwen/Qwen2.5-Coder-7B", and capabilities {"codeGeneration": 0.9, "testing": 0.7}
    Then the agent "agent-1" should be in the list of registered agents
    And the endpoint for "agent-1" should be "http://localhost:8000"
    And the agent config for "agent-1" should have modelName "Qwen/Qwen2.5-Coder-7B"

  Scenario: Register multiple agents
    Given a capability registry
    And an EffGenAdapter initialized with the registry
    When I register an agent with agentRef "agent-1", endpoint "http://localhost:8000", modelName "Qwen/Qwen2.5-Coder-7B", and capabilities {}
    And I register an agent with agentRef "agent-2", endpoint "http://localhost:8001", modelName "Qwen/Qwen2.5-Coder-3B", and capabilities {}
    Then the list of registered agents should contain ["agent-1", "agent-2"]

  Scenario: Get endpoint for registered agent
    Given a capability registry
    And an EffGenAdapter initialized with the registry
    And an agent "agent-1" is registered with endpoint "http://localhost:8000"
    When I get the endpoint for "agent-1"
    Then the endpoint should be "http://localhost:8000"

  Scenario: Get endpoint for unregistered agent
    Given a capability registry
    And an EffGenAdapter initialized with the registry
    When I get the endpoint for "nonexistent-agent"
    Then the endpoint should be None

  Scenario: Check health of unregistered agent
    Given a capability registry
    And an EffGenAdapter initialized with the registry
    When I check health for "nonexistent-agent"
    Then the health status should be "unknown"
    And the health error should be "Agent not registered"

  Scenario: Check health of registered agent
    Given a capability registry
    And an EffGenAdapter initialized with the registry
    And an agent "agent-1" is registered with endpoint "http://localhost:8000"
    When I check health for "agent-1"
    Then the health status should be "unknown"
    And the health error should be None

  Scenario: Get configuration for registered agent
    Given a capability registry
    And an EffGenAdapter initialized with the registry
    And an agent "agent-1" is registered with endpoint "http://localhost:8000", modelName "Qwen/Qwen2.5-Coder-7B", isMultiAgent True, and teamMembers ["agent-2", "agent-3"]
    When I get the agent config for "agent-1"
    Then the config should have agentRef "agent-1"
    And the config should have endpoint "http://localhost:8000"
    And the config should have modelName "Qwen/Qwen2.5-Coder-7B"
    And the config should have isMultiAgent True
    And the config should have teamMembers ["agent-2", "agent-3"]

  Scenario: Get configuration for unregistered agent
    Given a capability registry
    And an EffGenAdapter initialized with the registry
    When I get the agent config for "nonexistent-agent"
    Then the config should be None

  Scenario: List agents when none registered
    Given a capability registry
    And an EffGenAdapter initialized with the registry
    When I list all agents
    Then the list should be empty

  Scenario: Serialize TaskRequest to MCP parameters
    Given a TaskRequest with taskId "task-123", taskType "code_generation", prompt "Write a function", and context {"language": "python"}
    When I convert it to MCP parameters
    Then the parameters should have taskId "task-123"
    And the parameters should have taskType "code_generation"
    And the parameters should have prompt "Write a function"
    And the parameters should have context {"language": "python"}

  Scenario: Parse TaskResponse from MCP response
    Given an MCP response with taskId "task-456", output "def foo(): pass", tokensUsed 50, and success True
    When I create a TaskResponse from the MCP response
    Then the TaskResponse should have taskId "task-456"
    And the TaskResponse should have output "def foo(): pass"
    And the TaskResponse should have tokensUsed 50
    And the TaskResponse should have success True

  Scenario: Parse TaskResponse from minimal MCP response
    Given an MCP response with only taskId "task-789"
    When I create a TaskResponse from the MCP response
    Then the TaskResponse should have taskId "task-789"
    And the TaskResponse should have output ""
    And the TaskResponse should have tokensUsed 0
    And the TaskResponse should have success False