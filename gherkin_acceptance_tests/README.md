# OAuth Acceptance Tests

This directory contains Gherkin acceptance tests for the Autonomous TDD Agent demo.

## Structure

```
gherkin_acceptance_tests/
├── oauth.feature           # Gherkin scenarios defining OAuth requirements
├── steps/
│   └── oauth_steps.py      # Python step definitions
└── README.md              # This file
```

## Test Scenarios

The `oauth.feature` file defines 5 acceptance test scenarios:

1. **Create OAuth client with configuration** - Verify client initialization
2. **Generate authorization URL** - Test URL generation with parameters
3. **Exchange authorization code for access token** - Test token exchange flow
4. **Validate access token** - Test token validation and metadata retrieval
5. **Refresh expired access token** - Test token refresh flow

## Step Definitions

The `steps/oauth_steps.py` file implements the step definitions that connect Gherkin scenarios to the generated OAuth implementation code.

- Uses behave decorators: `@given`, `@when`, `@then`
- Imports generated OAuth code from `/tmp/oauth_auth_demo/src/`
- Stores test context (client, tokens, etc.) in behave `context` object

## Running Tests

### Standalone (against existing generated code)

```bash
# From project root
behave gherkin_acceptance_tests --no-capture
```

### With TDD Agent Demo

The `demo_gherkin_tdd.py` script automatically uses these tests:

```bash
python3 demo_gherkin_tdd.py
```

The agent will:
1. Read these Gherkin scenarios for requirements
2. Use emergent TDD to build incrementally
3. Check acceptance tests every 3 cycles
4. Stop when ALL scenarios pass

## Test Results

**Status**: All 5 scenarios passing (28 steps)

```
1 feature passed, 0 failed, 0 skipped
5 scenarios passed, 0 failed, 0 skipped
28 steps passed, 0 failed, 0 skipped
```

The generated OAuth implementation successfully:
- Creates OAuth clients with configuration
- Generates authorization URLs with all required parameters
- Exchanges authorization codes for access tokens
- Validates access tokens and retrieves metadata
- Refreshes expired tokens

## Modifying Tests

To add new scenarios or modify existing ones:

1. **Edit `oauth.feature`** - Add new Gherkin scenarios using Given/When/Then syntax
2. **Update `steps/oauth_steps.py`** - Implement corresponding step definitions
3. **Test manually** - Run `behave gherkin_acceptance_tests` to verify
4. **Run full demo** - Execute `demo_gherkin_tdd.py` to see agent work toward new requirements

## Example Scenario

```gherkin
Scenario: Create OAuth client with configuration
  Given I have OAuth provider credentials
  When I create an OAuth client with client_id and client_secret
  Then the OAuth client should be properly configured
  And the client should have the correct redirect URI
```

## Notes

- These tests are **permanent** and stored in version control
- The demo uses these tests, not temporary `/tmp` files
- Step definitions dynamically import generated code from `/tmp/oauth_auth_demo/`
- The agent can see these scenarios to guide test planning
