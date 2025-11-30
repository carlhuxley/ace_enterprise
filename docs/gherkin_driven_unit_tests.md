# Gherkin-Driven Unit Test Architecture

**Status:** ✅ Implemented
**Date:** 2025-11-29
**Approach:** Simplified ATDD - Gherkin drives unit test generation without step definitions

---

## Overview

The autonomous TDD agent now uses **Gherkin scenarios to directly drive unit test generation**, eliminating the need for step definitions during development. This provides the benefits of business-readable requirements (Gherkin) while keeping the development workflow simple and fast.

## Architecture

```
┌─────────────────────────┐
│  Gherkin Scenarios      │  Business requirements in natural language
│  (.feature files)       │
└───────────┬─────────────┘
            │
            │ LLM reads and parses
            ↓
┌─────────────────────────┐
│  Parsed Scenarios       │  Structured data: Given/When/Then steps
│  (in memory)            │
└───────────┬─────────────┘
            │
            │ LLM derives unit tests
            ↓
┌─────────────────────────┐
│  Unit Tests             │  Comprehensive, contract-focused tests
│  (test_*.py)            │  Uses mocking for isolation
└───────────┬─────────────┘
            │
            │ RED → GREEN → REFACTOR
            ↓
┌─────────────────────────┐
│  Implementation         │  Production code
│  (src/*.py)             │
└─────────────────────────┘
```

## How It Works

### 1. Write Gherkin Scenarios

**Example:** `gherkin_acceptance_tests/oauth.feature`
```gherkin
Feature: OAuth Authentication
  As a third-party application
  I want to authenticate users via OAuth
  So that users can grant me access without sharing passwords

  Scenario: User grants application access
    Given a user wants to authorize my application
    When I redirect them to the OAuth provider with required parameters
    Then they should see a valid authorization URL
    And the URL should include CSRF protection
```

### 2. Agent Parses Scenarios

**Code:** `src/agents/autonomous_tdd_agent.py:2331-2400`

The agent extracts:
- Scenario name: "User grants application access"
- Given steps: ["a user wants to authorize my application"]
- When steps: ["I redirect them to the OAuth provider with required parameters"]
- Then steps: ["they should see a valid authorization URL", "the URL should include CSRF protection"]

### 3. LLM Generates Unit Tests

The LLM receives:
- Parsed Gherkin scenarios
- Current implementation state
- Instructions to derive tests that satisfy the business requirements

**Generated tests:**
```python
def test_generate_authorization_url_returns_valid_url():
    client = OAuthClient(...)
    url = client.generate_authorization_url(...)
    assert "https://example.com/auth" in url
    assert "client_id=test_id" in url

def test_generate_authorization_url_includes_state_parameter_for_csrf_protection():
    client = OAuthClient(...)
    url = client.generate_authorization_url(..., state="random_state_string")
    assert "state=random_state_string" in url
```

### 4. TDD Cycle: RED → GREEN → REFACTOR

Each test follows the standard TDD cycle:
- **RED:** Test fails (no implementation)
- **GREEN:** Minimal code to pass test
- **REFACTOR:** Improve code quality
- **LEARN:** Extract patterns to playbook

## Key Characteristics

### ✅ **What This Approach Provides**

1. **Business-readable requirements** - Gherkin scenarios define "what" to build
2. **No step definitions needed** - Simpler architecture, fewer files
3. **Fast development cycle** - Unit tests with mocks are fast to run
4. **Comprehensive test coverage** - LLM generates thorough tests from scenarios
5. **Contract-focused tests** - Tests verify API contracts, not implementation details

### ⚠️ **What This Approach Doesn't Provide**

1. **End-to-end verification** - Unit tests use mocking (not real integrations)
2. **Acceptance test automation** - No executable acceptance tests (yet)
3. **Real API contract validation** - Mocks may not match actual API behavior

## Differences from Traditional ATDD/BDD

| Aspect | Traditional BDD/ATDD | Our Gherkin-Driven Approach |
|--------|----------------------|------------------------------|
| **Step definitions** | Required (Python code mapping Gherkin → tests) | Not used |
| **Acceptance tests** | Executable via `behave` | Not generated (optional future enhancement) |
| **Test type** | End-to-end (real integrations) | Unit tests (mocked dependencies) |
| **Speed** | Slower (real HTTP calls, databases) | Faster (mocked responses) |
| **When to use** | Final verification after implementation | During development |

## Example: OAuth Feature

### Gherkin Input (3 scenarios)
```gherkin
Scenario: User grants application access
Scenario: Application receives access after user authorization
Scenario: Application maintains access using refresh tokens
```

### Generated Output

**10 unit tests:**
- `test_oauth_client_can_be_created()`
- `test_generate_authorization_url_returns_valid_url()`
- `test_generate_authorization_url_includes_state_parameter_for_csrf_protection()`
- `test_exchange_authorization_code_for_tokens()`
- `test_refresh_access_token_returns_new_access_token()`
- `test_validate_access_token_returns_true_for_valid_token()`
- (+ 4 more verification tests)

**Implementation:**
- Complete `OAuthClient` class
- All methods: `generate_authorization_url()`, `exchange_authorization_code_for_tokens()`, `refresh_access_token()`, `validate_access_token()`
- OAuth2 spec compliant
- Proper URL encoding, HTTP headers

## Future Enhancement: Add ATDD Later

This architecture can be enhanced to full ATDD **without major refactoring**:

```
┌─────────────────────────┐
│  Gherkin Scenarios      │
└───────────┬─────────────┘
            │
            ├─────────────────────────┐
            │                         │
            ↓                         ↓
┌─────────────────────────┐   ┌──────────────────────┐
│  Unit Tests             │   │  Step Definitions    │  (NEW)
│  (development)          │   │  (acceptance)        │
└─────────────────────────┘   └──────────┬───────────┘
                                         │
                                         ↓
                              ┌──────────────────────┐
                              │  Acceptance Tests    │  (NEW)
                              │  (end-to-end)        │
                              └──────────────────────┘
```

**To add ATDD:**
1. Generate step definitions from Gherkin scenarios
2. Run `behave` to execute acceptance tests
3. Use acceptance tests for final integration verification
4. Keep unit tests for fast development feedback

**Minimal refactoring needed** because:
- Gherkin scenarios already exist ✓
- Implementation already exists ✓
- Just add: step definition generation + acceptance test execution

## Configuration

**Enable Gherkin-driven planning:**
```python
agent = AutonomousTDDAgent(...)
result = agent.build_feature(
    requirement="OAuth authentication system...",
    gherkin_dir=Path("gherkin_acceptance_tests")  # ← Provide Gherkin directory
)
```

**Agent behavior:**
- If `gherkin_dir` provided + `.feature` file exists → **Gherkin-driven planning**
- Otherwise → **Emergent planning** (LLM decides tests based on current state)

**Output:**
```
💡 Using GHERKIN-DRIVEN planning (3 scenarios)
📋 Acceptance tests from: oauth.feature
```

## Code References

**Key files:**
- `src/agents/autonomous_tdd_agent.py:2331-2400` - Gherkin parser (`_parse_gherkin_scenarios()`)
- `src/agents/autonomous_tdd_agent.py:188-201` - Gherkin-driven mode detection
- `src/agents/autonomous_tdd_agent.py:433-525` - Test planning with Gherkin context

**Demo:**
- `demo_gherkin_tdd.py` - Demonstrates Gherkin-driven TDD
- `gherkin_acceptance_tests/oauth.feature` - Example Gherkin scenarios

## Benefits vs Traditional TDD

| Traditional TDD | Gherkin-Driven TDD |
|-----------------|---------------------|
| Developer decides what to test | Business requirements drive tests |
| Tests may miss business scenarios | Tests map directly to scenarios |
| No business-readable documentation | Gherkin serves as living documentation |
| Implementation-focused tests | Contract-focused tests |

## Limitations & Trade-offs

**Limitations:**
1. **No end-to-end verification** - Unit tests use mocking
2. **Mock accuracy** - Mocks may not match real API behavior
3. **Integration bugs** - May slip through if mocks are incorrect

**Trade-offs:**
- **Speed vs Coverage:** Fast unit tests vs comprehensive integration tests
- **Simplicity vs Completeness:** No step definitions vs full ATDD
- **Development vs Deployment:** Great for dev, may need integration tests for prod

**When to add acceptance tests:**
- Before production deployment
- For critical integrations (OAuth providers, payment APIs)
- When unit test mocks don't match reality

## Conclusion

The **Gherkin-Driven Unit Test** approach provides:
- Business-readable requirements (Gherkin)
- Automated test generation (LLM)
- Fast development cycle (unit tests)
- Simple architecture (no step definitions)

**It's ideal for:**
- Rapid prototyping
- Development phase
- Teams that want BDD-style requirements without full ATDD overhead

**Consider full ATDD when:**
- You need end-to-end verification
- Integration accuracy is critical
- You're ready for production deployment

---

**Next Steps:**
1. ✅ Gherkin-driven unit tests working
2. 🔜 Improve code quality (error handling, validation)
3. 🔜 Add step definition generation (optional)
4. 🔜 Add acceptance test execution (optional)
