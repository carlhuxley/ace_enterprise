Feature: Application Settings Configuration

  Scenario: Default settings load with sensible defaults when no overrides are provided
    Given no environment variables or .env overrides are set
    When Settings is instantiated
    Then env is "development"
    And debug is False
    And api_port is 8000
    And default_llm_provider is "ollama"
    And log_level is "INFO"

  Scenario: Environment mode helper properties reflect the configured environment
    Given Settings is instantiated with env set to "production"
    When is_development is accessed
    Then it returns False
    And is_production returns True

  Scenario: Development environment is correctly identified via helper properties
    Given Settings is instantiated with env set to "development"
    When is_development is accessed
    Then it returns True
    And is_production returns False

  Scenario: Invalid environment value is rejected
    Given a settings override of env set to "staging2"
    When Settings is instantiated
    Then a validation error is raised

  Scenario: Wildcard CORS origins combined with allow credentials is rejected
    Given cors_origins is set to a list containing "*"
    And cors_allow_credentials is set to True
    When Settings is instantiated
    Then a validation error is raised stating that cors_allow_credentials cannot be combined with a wildcard cors_origins

  Scenario: Wildcard CORS origins are allowed when credentials are disabled
    Given cors_origins is set to a list containing "*"
    And cors_allow_credentials is set to False
    When Settings is instantiated
    Then the settings instance is created successfully

  Scenario: Default model id resolves according to the selected provider
    Given default_llm_provider is set to "anthropic"
    And anthropic_default_model is set to "claude-sonnet-4-20250514"
    When default_model_id is accessed
    Then it returns "claude-sonnet-4-20250514"

  Scenario: Cached settings retrieval returns the same instance on repeated calls
    Given get_settings has already been called once
    When get_settings is called again
    Then the same Settings instance is returned without re-reading the environment