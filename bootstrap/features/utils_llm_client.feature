Feature: LLM Client unified provider interface

  Scenario: Requesting generation from an unsupported provider fails fast
    Given an LLM client configured with provider "carrier-pigeon" and model "v1"
    When I call generate with prompt "Hello, world"
    Then a ValueError is raised with message "Unsupported provider: carrier-pigeon"

  Scenario: Successful generation returns a normalized result envelope
    Given an LLM client configured with provider "ollama" and model "llama3"
    And the Ollama server at the configured base URL responds successfully with response text "Hi there!", prompt_eval_count 5, and eval_count 3
    When I call generate with prompt "Say hi"
    Then the result contains content "Hi there!"
    And the result contains tokens_used 8
    And the result contains model "llama3"
    And the result contains a non-negative integer latency_ms

  Scenario: vLLM provider without a base URL fails before making any request
    Given an LLM client configured with provider "vllm" and model "mistral-7b" and no base_url
    When I call generate with prompt "Summarize this text"
    Then a ValueError is raised with message "vLLM provider requires base_url to be specified"

  Scenario: OpenAI provider without a configured API key fails before making any request
    Given an LLM client configured with provider "openai" and model "gpt-4o" and no OpenAI API key configured
    When I call generate with prompt "Write a haiku"
    Then a ValueError is raised with message "OpenAI API key not configured"

  Scenario: OpenRouter provider reports quota exhaustion as a distinct, non-retryable error
    Given an LLM client configured with provider "openrouter" and model "gpt-4o" with a valid OpenRouter API key
    And the OpenRouter API responds with HTTP status 402 and body "insufficient credit"
    When I call generate with prompt "Explain quantum computing"
    Then an LLMQuotaExhaustedError is raised
    And no further retry requests are made

  Scenario: check_availability reflects whether an API provider has a configured key
    Given an LLM client configured with provider "anthropic" and model "claude-3" with no Anthropic API key configured
    When I call check_availability
    Then the result is False

  Scenario: check_availability reflects whether the local Ollama server responds
    Given an LLM client configured with provider "ollama" and model "llama3"
    And the Ollama server at the configured base URL is unreachable
    When I call check_availability
    Then the result is False

  Scenario Outline: extract_model_version picks the first matching header in priority order
    Given response headers <headers>
    When I call extract_model_version with those headers
    Then the result is "<version>"

    Examples:
      | headers                                                              | version        |
      | {"X-Model-Version": "gpt-4o-2024-08-06"}                             | gpt-4o-2024-08-06 |
      | {"x-openrouter-model": "anthropic/claude-3-opus", "x-model": "other"} | anthropic/claude-3-opus |
      | {}                                                                    | None           |