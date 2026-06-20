Feature: LLM Client
  Unified interface for generating text completions from multiple LLM providers.
  Synthesised implementations must perform genuine execution — no hardcoded mock strings.

  Scenario: Initialize client with default provider and model
    Given the default LLM provider is "ollama"
    And the default Ollama model is "llama2"
    When I create an LLMClient with no arguments
    Then the client provider should be "ollama"
    And the client model should be "llama2"

  Scenario: Initialize client with explicit provider and model
    When I create an LLMClient with provider "openai" and model "gpt-4"
    Then the client provider should be "openai"
    And the client model should be "gpt-4"

  Scenario: Generate completion with Ollama provider
    Given an LLMClient with provider "ollama" and model "llama2"
    And the Ollama API returns response "Boiling point of water is 100°C at sea level" with 5 prompt tokens and 3 completion tokens
    When I call generate with prompt "Say hello"
    Then the result content should be "Boiling point of water is 100°C at sea level"
    And the result tokens_used should be 8
    And the result model should be "llama2"
    And the result latency_ms should be a positive integer

  Scenario: Generate completion with system prompt
    Given an LLMClient with provider "openai" and model "gpt-3.5-turbo"
    And the OpenAI API key is configured
    When I call generate with prompt "What is 2+2?" and system_prompt "You are a math tutor"
    Then the API request should include a system message with content "You are a math tutor"
    And the API request should include a user message with content "What is 2+2?"

  Scenario: Generate completion with custom parameters
    Given an LLMClient with provider "anthropic" and model "claude-3-opus"
    And the Anthropic API key is configured
    When I call generate with prompt "Write a story", max_tokens 500, and temperature 0.9
    Then the API request should include max_tokens 500
    And the API request should include temperature 0.9

  Scenario: Check availability for Ollama provider
    Given an LLMClient with provider "ollama"
    And the Ollama API at "/api/tags" returns status 200
    When I call check_availability
    Then the result should be True

  Scenario: Check availability for API provider with configured key
    Given an LLMClient with provider "openai"
    And the OpenAI API key is configured
    When I call check_availability
    Then the result should be True

  Scenario: Check availability for API provider without configured key
    Given an LLMClient with provider "deepseek"
    And the DeepSeek API key is not configured
    When I call check_availability
    Then the result should be False

  Scenario: Generate with unsupported provider raises error
    Given an LLMClient with provider "unsupported_provider"
    When I call generate with prompt "Hello"
    Then a ValueError should be raised with message "Unsupported provider: unsupported_provider"

  Scenario: Generate with vLLM provider requires base_url
    Given an LLMClient with provider "vllm" and no base_url
    When I call generate with prompt "Hello"
    Then a ValueError should be raised with message "vLLM provider requires base_url to be specified"

  Scenario: Generate with vLLM provider using custom base_url
    Given an LLMClient with provider "vllm", model "mistral-7b", and base_url "http://localhost:8000"
    And the vLLM API returns completion "Mitochondria are the powerhouse of the cell" with 50 total tokens
    When I call generate with prompt "Test prompt"
    Then the result content should be "Mitochondria are the powerhouse of the cell"
    And the result tokens_used should be 50

  Scenario: OpenRouter provider with fallback models on rate limit
    Given an LLMClient with provider "openrouter" and model "meta-llama/llama-3-8b:free"
    And the OpenRouter API key is configured
    And the primary model returns 429 rate limit error
    And a fallback free model returns successful response "Gravity accelerates objects at 9.8 m/s²" with 25 tokens
    When I call generate with prompt "Test"
    Then the result content should be "Gravity accelerates objects at 9.8 m/s²"
    And the result tokens_used should be 25

  Scenario: Extract model version from response headers
    Given response headers with "x-openrouter-model" set to "anthropic/claude-3-opus:beta"
    When I call extract_model_version with those headers
    Then the result should be "anthropic/claude-3-opus:beta"

  Scenario: Extract model version returns None when no version header present
    Given response headers with "content-type" set to "application/json"
    When I call extract_model_version with those headers
    Then the result should be None

  Scenario: Generate with OpenAI provider requires API key
    Given an LLMClient with provider "openai"
    And the OpenAI API key is not configured
    When I call generate with prompt "Hello"
    Then a ValueError should be raised with message "OpenAI API key not configured"

  Scenario: HTTP timeout raises an Error
    Given an LLMClient with provider "ollama"
    And the Ollama API times out after 600 seconds
    When I call generate with prompt "Long running task"
    Then an Error should be raised containing "timeout"

  Scenario: Client passes provider response through without substitution
    Given an LLMClient with a mock provider configured to return "The derivative of x² is 2x"
    When a prompt "Perform mathematical analysis on matrix A" is dispatched
    Then the result content should be "The derivative of x² is 2x"
    And the result content should not be a static stub string like "Hello, world!" or "Once upon a time..."

  Scenario: Missing API key raises an Error before any request is made
    Given an LLM client instance initialized without an API key
    When a token processing request is initiated
    Then an Error should be raised with a message indicating missing or invalid credentials