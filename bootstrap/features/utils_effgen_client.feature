Feature: effGen Local LLM Client
  As a caller needing local LLM inference
  I want to generate text and check availability via EffGenClient
  So that I can use local models instead of external APIs

  Scenario: Creating a client when the effGen environment is missing
    Given no effGen installation exists at "/home/user/effgen_test"
    When I create an EffGenClient with model "Qwen/Qwen2.5-1.5B-Instruct" and effgen_path "/home/user/effgen_test"
    Then a ValueError is raised
    And the error message mentions "effGen Python not found"

  Scenario: Creating a client when the effGen environment is present
    Given a valid effGen installation exists at "/home/user/effgen_test" with a Python interpreter in ".venv/bin/python"
    When I create an EffGenClient with model "Qwen/Qwen2.5-1.5B-Instruct", quantization "4bit", and effgen_path "/home/user/effgen_test"
    Then the client is created successfully
    And the client's provider is "effgen"
    And the client's model is "Qwen/Qwen2.5-1.5B-Instruct"

  Scenario: Generating text successfully
    Given a valid EffGenClient configured with model "Qwen/Qwen2.5-1.5B-Instruct"
    And the underlying model returns the text "The sum of 2 and 3 is 5." with 12 tokens used
    When I call generate with prompt "Write a function that adds two numbers"
    Then the result contains "content" equal to "The sum of 2 and 3 is 5."
    And the result contains "tokens_used" equal to 12
    And the result contains "model" equal to "Qwen/Qwen2.5-1.5B-Instruct"
    And the result contains a "latency_ms" value greater than or equal to 0

  Scenario: Generating text with a system prompt included
    Given a valid EffGenClient configured with model "Qwen/Qwen2.5-1.5B-Instruct"
    And the underlying model echoes back whatever prompt text it receives
    When I call generate with prompt "What is your role?" and system_prompt "You are a helpful coding assistant."
    Then the result's "content" includes both the system prompt text and the user prompt text

  Scenario: Generation times out
    Given a valid EffGenClient configured with a timeout of 5.0 seconds
    And the underlying generation process does not complete within 5.0 seconds
    When I call generate with prompt "Solve a hard problem"
    Then a RuntimeError is raised
    And the error message mentions "effGen timeout after 5.0s"

  Scenario: Generating text using the agent mode with tools
    Given a valid EffGenClient configured with model "Qwen/Qwen2.5-1.5B-Instruct"
    And the underlying agent run returns the output "Tests pass: 3/3"
    When I call generate_with_agent with prompt "Run the test suite" and tools ["PythonREPL", "CodeExecutor"]
    Then the result contains "content" equal to "Tests pass: 3/3"
    And the result contains "agent_mode" equal to true
    And the result contains "model" equal to "Qwen/Qwen2.5-1.5B-Instruct"

  Scenario: Checking availability when the model loads successfully
    Given a valid EffGenClient configured with model "Qwen/Qwen2.5-1.5B-Instruct"
    And the underlying environment can load the model and print "OK"
    When I call check_availability
    Then the result is true

  Scenario: Checking availability when the model fails to load
    Given a valid EffGenClient configured with model "Qwen/Qwen2.5-1.5B-Instruct"
    And the underlying environment fails to load the model
    When I call check_availability
    Then the result is false

  Scenario: Using the factory function to create a client
    Given a valid effGen installation exists at the default path "~/effgen_test"
    When I call get_effgen_client with model "Qwen/Qwen2.5-1.5B-Instruct" and quantization "8bit"
    Then an EffGenClient instance is returned
    And its model is "Qwen/Qwen2.5-1.5B-Instruct"