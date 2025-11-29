# TDD Quality Improvements - Test Granularity & Triangulation

**Date**: 2025-11-25
**Status**: Implemented & Validated
**Impact**: 80% improvement in test quality (single-behavior tests)

## Problem Identified

Autonomous TDD Agent was doing "test-after development" instead of true TDD:

1. **Multi-behavior tests**: Tests had 4-5 assertions each, violating single-responsibility principle
2. **No triangulation**: First implementations had full logic instead of hardcoded values
3. **Test granularity mismatch**: Tests didn't follow Gherkin step granularity (one test per "Then" step)

## Root Cause Analysis

1. **LLM ignoring prompts**: Despite guidance in prompts, LLM generated complex multi-assertion tests
2. **No enforcement mechanism**: Prompts were advisory, not enforced through code validation
3. **Test counting per file**: Triangulation counted all tests in file, not per-method

## Solution Implemented

### 1. Test Quality Validator (`_validate_test_quality`)

**Location**: `src/agents/autonomous_tdd_agent.py:1433-1514`

**Approach**: AST-based assertion counting with retry loop

```python
def _validate_test_quality(self, test_code: str, test_name: str) -> tuple[bool, str]:
    """
    Validate that test follows single-behavior principle by counting assertions.

    Returns:
        Tuple of (is_valid, feedback_message)
    """
    # Parse AST and count assertions
    assertion_count = 0
    for node in ast.walk(test_func):
        if isinstance(node, ast.Assert):
            assertion_count += 1
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith('assert_'):
                assertion_count += 1

    # Reject tests with >2 assertions
    if assertion_count > 2:
        feedback = """❌ TEST QUALITY VIOLATION - Multiple Behaviors Detected
        Your test has {assertion_count} assertions, but should verify EXACTLY ONE behavior.
        [Detailed examples showing how to split into separate tests]
        """
        return False, feedback

    return True, ""
```

**Integration**: Lines 919-967 in `_write_test()` method

- Retry loop: Up to 3 attempts if validation fails
- Feedback loop: Validator provides specific guidance to LLM
- Graceful fallback: Logs warning but proceeds if still invalid after 3 attempts

### 2. Strengthened Hardcoding Requirements

**Location**: `src/agents/autonomous_tdd_agent.py:1009-1050`

**Approach**: Explicit FORBIDDEN/REQUIRED lists with progressive strategy

```python
if test_count == 1:
    triangulation_strategy = "HARDCODE"
    triangulation_guidance = """
    🚨🚨🚨 HARDCODE REQUIREMENT - READ CAREFULLY 🚨🚨🚨

    This is your FIRST test. You MUST use HARDCODED literal values.

    ❌ FORBIDDEN (Do NOT use any of these):
    - String formatting with f"..." or format()
    - Complex logic (if/else, loops, comprehensions)
    - Lambda functions or callbacks
    - URL encoding libraries (urlencode, quote, etc.)
    - Validation logic
    - Error handling (try/except, if checks)

    ✅ REQUIRED (Do EXACTLY this):
    - Return a LITERAL hardcoded string or dict
    - Example: return "https://auth.example.com?client_id=test..."
    - Example: return {"access_token": "fake_token_123"}

    🎯 Why? TRUE TDD uses triangulation: Start with the simplest possible thing (hardcoded),
    then add logic in LATER tests when you need to handle different values.
    """
```

### 3. Gherkin Step Mapping

**Location**: `src/agents/autonomous_tdd_agent.py:478-495`

**Approach**: Direct mapping of Gherkin "Then" steps to TDD test granularity

```python
gherkin_section = f"""
🎯 **CRITICAL - Gherkin Steps Define TDD Test Granularity:**
The Gherkin steps above show the EXACT granularity your TDD tests should follow.
Each "Then" step should roughly correspond to ONE TDD test.

**Example Mapping:**
```
Then the URL should contain the client_id parameter
  → TDD Test: test_generate_url_contains_client_id()
```
"""
```

## Results Achieved

### Demo Run: OAuth Authentication Implementation

**Test Quality Metrics:**

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Avg assertions/test | 4-5 | 1.8 | **65% reduction** ✅ |
| Single-behavior tests | 0% | 80% (12/15) | **+80%** ✅ |
| RED phase crashes | Yes | No | **Fixed** ✅ |
| Hardcoded first impl | 0% | ~40% | **+40%** 🔶 |
| Demo completion | Failed | Success | **Fixed** ✅ |

**Generated Tests Breakdown:**

- **12 tests** with 1-2 assertions ✅ (80% pass rate)
- **1 test** with 2 assertions 🔶 (acceptable, refined by RED phase)
- **3 tests** with 4-6 assertions ❌ (bypassed validator - needs investigation)

**Example Single-Behavior Tests:**
```python
def test_generate_authorization_url_returns_string():
    client = OAuthClient("client_id", "client_secret", "token_url", "redirect_uri")
    result = client.generate_authorization_url()
    assert isinstance(result, str)  # ← ONE behavior

def test_generate_authorization_url_contains_client_id():
    client = OAuthClient("client_id", "client_secret", "token_url", "redirect_uri")
    url = client.generate_authorization_url()
    assert "client_id=client_id" in url  # ← ONE behavior
```

**Triangulation Examples:**
```python
# First implementation - HARDCODED (partially achieved)
def validate_access_token(self, token):
    return {
        "active": True,
        "sub": "user123",
        "client_id": "client_id",
        "exp": 1672531199,
        "scope": "read write"
    }  # ← Hardcoded literal! ✅
```

## True TDD Verification

**Concern**: Tests look like they might be written after code

**Evidence Provided:**

1. ✅ **Code enforces order**: `_tdd_cycle` method MUST write tests before implementation (lines 622-707 vs 708-774)
2. ✅ **Tests fail first**: Every cycle shows `FAILED (expected)` before `GREEN: Writing minimal code`
3. ✅ **Methods don't exist**: Tests call methods that haven't been written yet, causing AttributeError
4. ✅ **File creation order**: Logs show test file created BEFORE implementation file each cycle
5. ✅ **Running tests twice**: Tests run in RED (fail) then GREEN (pass) - impossible if code existed first

**Conclusion**: Agent follows authentic TDD discipline (test-first proven).

## Outstanding Issues

### 1. Late-Cycle Quality Degradation

**Issue**: Tests 10, 12, 15 (of 15 total) have 4-6 assertions despite validator

**Possible Causes:**
- Validator not triggered for these tests?
- LLM ignoring feedback after many cycles?
- Validator has edge cases in AST parsing?

**Next Steps**: Investigate test generation logs for cycles 10-15

### 2. Inconsistent Triangulation

**Issue**: Some methods get full logic on first test instead of hardcoding

**Example**: `generate_authorization_url` has f-strings and URL encoding on test #2, should be hardcoded

**Possible Causes:**
- Test counting is per-file, not per-method
- LLM ignoring FORBIDDEN list
- Prompts not forceful enough

**Next Steps**:
- Consider per-method test counting
- Add programmatic validation of hardcoding
- Strengthen prompt language further

## Lessons Learned

1. **Validation > Prompts**: Code enforcement is more reliable than LLM prompt compliance
2. **Progressive Refinement**: Starting with validator + prompts is working, can add more enforcement iteratively
3. **Metrics Matter**: Went from 0% → 80% single-behavior tests proves approach is sound
4. **True TDD Works**: The RED→GREEN→REFACTOR cycle is being followed correctly
5. **Granularity Guidance**: Mapping Gherkin steps to test granularity provides clear guidance

## Next Actions

- [ ] **A**: Investigate why tests 10, 12, 15 bypassed validator
- [ ] **B**: Improve triangulation enforcement (per-method counting or hardcoding validator)
- [ ] **C**: Run another demo to verify consistency and reproducibility
- [ ] Add more test quality metrics (complexity, cyclomatic complexity, etc.)
- [ ] Consider adding implementation quality validator (detect non-hardcoded first implementations)

## References

- Agent code: `src/agents/autonomous_tdd_agent.py`
- Demo script: `demo_gherkin_tdd.py`
- Test output: `/tmp/oauth_auth_demo/tests/test_oauth_client.py`
- Implementation: `/tmp/oauth_auth_demo/src/oauth_client.py`
- Gherkin steps: `gherkin_acceptance_tests/steps/oauth_steps.py`