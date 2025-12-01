Feature: OAuth Authentication
  As a third-party application
  I want to authenticate users via OAuth
  So that users can grant me access without sharing passwords

  Scenario: User grants application access
    Given a user wants to authorize my application
    When I redirect them to the OAuth provider with required parameters
    Then they should see a valid authorization URL
    And the URL should include CSRF protection

  Scenario: Application receives access after user authorization
    Given a user has authorized my application
    When I exchange the authorization code for tokens
    Then I should receive a complete token response
    And I can use the access token to call protected APIs

  Scenario: Application maintains access using refresh tokens
    Given my access token has expired
    When I use the refresh token to request new credentials
    Then I should receive fresh tokens without user interaction
