Feature: EffGen Client LLM Interface
  As a user of the EffGen client
  I want to generate text completions using local models
  So that I can perform LLM inference without external APIs

  Scenario: Initialize client with default settings
    Given no custom configuration is provided
    When I create an EffGenClient instance
    Then the client should use model "Qwen/Qwen2.5-1.5B-Instruct"
    And the client should use quantization "4bit"
    And the client should have provider "effgen"
    And the client should have timeout 120.0 seconds

  Scenario: Initialize client with custom model and quantization
    Given I want to use model "Qwen/Qwen2.5-3B-Instruct"
    And I want to use quantization "8bit"
    When I create an EffGenClient with model "Qwen/Qwen2.5-3B-Instruct" and quantization "8bit"
    Then the client should use model "Qwen/Qwen2.5-3B-Instruct"
    And the client should use quantization "8bit"

  Scenario: Generate text completion with simple prompt
    Given an EffGenClient instance exists
    When I call generate with prompt "Write a function that adds two numbers"
    Then the response should contain key "content" with generated text
    And the response should contain key "tokensUsed" with an integer value
    And the response should contain key "latencyMs" with an integer value
    And the response should contain key "model" with the model name

  Scenario: Generate text completion with system prompt
    Given an EffGenClient instance exists
    When I call generate with prompt "Write a test" and systemPrompt "You are a Python expert"
    Then the response should contain key "content" with generated text
    And the response should contain key "tokensUsed" with an integer value
    And the response should contain key "model" with the model name

  Scenario: Generate text with custom parameters
    Given an EffGenClient instance exists
    When I call generate with prompt "Hello", maxTokens 256, and temperature 0.5
    Then the response should contain key "content" with generated text
    And the response should contain key "tokensUsed" with an integer value
    And the response should contain key "latencyMs" with an integer value

  Scenario: Generate with agent mode using tools
    Given an EffGenClient instance exists
    When I call generateWithAgent with prompt "Calculate 2+2" and tools ["PythonREPL"]
    Then the response should contain key "content" with generated text
    And the response should contain key "tokensUsed" with an integer value
    And the response should contain key "latencyMs" with an integer value
    And the response should contain key "agentMode" with value true

  Scenario: Generate with agent using system prompt and multiple tools
    Given an EffGenClient instance exists
    When I call generateWithAgent with prompt "Test this code", systemPrompt "You are a tester", and tools ["PythonREPL", "CodeExecutor"]
    Then the response should contain key "content" with generated text
    And the response should contain key "agentMode" with value true
    And the response should contain key "model" with the model name

  Scenario: Check availability of effGen installation
    Given an EffGenClient instance exists
    When I call checkAvailability
    Then the method should return a boolean value indicating availability

  Scenario: Create client using factory function with defaults
    When I call getEffgenClient with no arguments
    Then I should receive an EffGenClient instance
    And the instance should use model "Qwen/Qwen2.5-1.5B-Instruct"
    And the instance should use quantization "4bit"

  Scenario: Create client using factory function with custom settings
    When I call getEffgenClient with model "Qwen/Qwen2.5-3B" and quantization "none"
    Then I should receive an EffGenClient instance
    And the instance should use model "Qwen/Qwen2.5-3B"
    And the instance should use quantization "none"