Feature: EffGen MCP Adapter

  Scenario: Register an effGen agent with declared capabilities
    Given an EffGen agent configuration with agent_ref "effgen-coder-1", endpoint "http://localhost:8090/mcp", model_name "Qwen/Qwen2.5-Coder-7B", and capabilities {"code_generation": 0.9}
    When the agent is registered with the adapter
    Then the agent_ref "effgen-coder-1" appears in the list of registered agents
    And the agent's capabilities are registered with the capability registry

  Scenario: Register an effGen agent with no declared capabilities
    Given an EffGen agent configuration with agent_ref "effgen-reviewer-1", endpoint "http://localhost:8091/mcp", model_name "Qwen/Qwen2.5-Coder-7B", and no capabilities
    When the agent is registered with the adapter
    Then the agent_ref "effgen-reviewer-1" appears in the list of registered agents
    And no capabilities are registered with the capability registry

  Scenario: Retrieve the endpoint of a registered agent
    Given an agent "effgen-coder-1" has been registered with endpoint "http://localhost:8090/mcp"
    When the endpoint for "effgen-coder-1" is requested
    Then the returned endpoint is "http://localhost:8090/mcp"

  Scenario: Retrieve the endpoint of an agent that was never registered
    Given no agent with agent_ref "effgen-unknown" has been registered
    When the endpoint for "effgen-unknown" is requested
    Then the result is None

  Scenario: Check health of an unregistered agent
    Given no agent with agent_ref "effgen-ghost" has been registered
    When the health of "effgen-ghost" is checked
    Then the health status is "unknown"
    And the health status includes the error "Agent not registered"

  Scenario: Check health of a registered agent
    Given an agent "effgen-coder-1" has been registered
    When the health of "effgen-coder-1" is checked
    Then the health status is "unknown"
    And the health status has no error

  Scenario: Retrieve full configuration for a registered agent
    Given an agent "effgen-coder-1" has been registered with model_name "Qwen/Qwen2.5-Coder-7B"
    When the agent configuration for "effgen-coder-1" is requested
    Then the returned configuration has model_name "Qwen/Qwen2.5-Coder-7B"

  Scenario: List all registered agents
    Given agents "effgen-coder-1" and "effgen-reviewer-1" have been registered
    When the list of registered agents is requested
    Then the list contains "effgen-coder-1" and "effgen-reviewer-1"