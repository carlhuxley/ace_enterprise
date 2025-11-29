Feature: OAuth Authentication
  As a user
  I want to authenticate using OAuth
  So that I can securely access protected resources

  Scenario: Create OAuth client with configuration
    Given I have OAuth provider credentials
    When I create an OAuth client with client_id and client_secret
    Then the OAuth client should be properly configured
    And the client should have the correct redirect URI

  Scenario: Generate authorization URL
    Given I have a configured OAuth client
    When I request an authorization URL with required scopes
    Then I should receive a valid authorization URL
    And the URL should contain the client_id parameter
    And the URL should contain the redirect_uri parameter
    And the URL should contain the scope parameter
    And the URL should contain a state parameter for CSRF protection

  Scenario: Exchange authorization code for access token
    Given I have a configured OAuth client
    And I have received an authorization code
    When I exchange the code for an access token
    Then I should receive an access token
    And I should receive a token type
    And the token should have an expiration time

  Scenario: Validate access token
    Given I have a configured OAuth client
    And I have a valid access token
    When I validate the access token
    Then the token should be verified as valid
    And I should be able to retrieve token metadata

  Scenario: Refresh expired access token
    Given I have a configured OAuth client
    And I have a refresh token
    When I use the refresh token to get a new access token
    Then I should receive a new access token
    And the new token should have a fresh expiration time
    And I should be able to use the new token for API calls
