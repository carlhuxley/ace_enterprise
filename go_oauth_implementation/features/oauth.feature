Feature: OAuth Authentication
  OAuth 2.0 client for authorization code flow.

  Scenario: Create oauth client
    Given a o auth client with client_id='test_client_id', client_secret='test_secret', auth_url='https://auth.example.com/oauth'
    Then client.client id should be 'test_client_id'
    Then client.client secret should be 'test_secret'
    Then client.auth url should be 'https://auth.example.com/oauth'

  Scenario: Generate authorization url with required params
    Given a o auth client with client_id='app_123', client_secret='secret', auth_url='https://auth.example.com/oauth'
    Then url should contain 'client_id=app_123'
    Then url should contain 'redirect_uri=https%3A%2F%2Fmyapp.com%2Fcallback'
    Then url should contain 'scope=read+write'
    Then url should contain 'response_type=code'

  Scenario: Generate authorization url with state
    Given a o auth client with client_id='app_123', client_secret='secret', auth_url='https://auth.example.com/oauth'
    Then url should contain 'state=random_csrf_token'

  Scenario: Exchange code for token
    Given a o auth client with client_id='app_123', client_secret='secret', auth_url='https://auth.example.com/oauth'
    Then token response['access token'] should pass validation
    Then token response['token type'] should be 'Bearer'
    Then token response['expires in'] should pass validation

