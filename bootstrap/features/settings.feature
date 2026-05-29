Feature: Application Settings
  Provides system configuration with environment-based defaults

  Scenario: Default settings include expected provider and environment
    Given no environment overrides are set
    When settings are loaded
    Then the default_llm_provider is a non-empty string
    And the env is a non-empty string

  Scenario: is_development is true when env is development
    Given settings with env "development"
    When is_development is accessed
    Then it returns true
    And is_production returns false

  Scenario: is_production is true when env is production
    Given settings with env "production"
    When is_production is accessed
    Then it returns true
    And is_development returns false

  Scenario: default_model_id reflects the configured provider and model
    Given settings with default_llm_provider "openai" and openai_default_model "gpt-4o-mini"
    When default_model_id is accessed
    Then it returns "gpt-4o-mini"

  Scenario: Settings instance is cached across calls
    When settings are loaded twice
    Then both calls return the same instance
