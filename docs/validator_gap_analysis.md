# Test Quality Validator - Gap Analysis

**Date**: 2025-11-25
**Issue**: 3/15 tests have 4-8 assertions despite validator

## Root Cause

**RED Phase Refinement Bypasses Validator**

Location: `src/agents/autonomous_tdd_agent.py:656-678`

```python
# Refine test to make it more specific/strict
refined_test_code = self._refine_test_to_fail(...)

# Update test code and test_functions array
test_code = refined_test_code

# ❌ NO VALIDATION HERE!
if test_file_key in self.test_functions:
    for func_data in self.test_functions[test_file_key]:
        if func_data['name'] == increment.test_name:
            func_data['code'] = refined_test_code  # ← Stored without validation
            break
```

## Evidence

Test #10: `test_oauth_client_constructor_accepts_optional_parameters`
- **8 assertions** found
- Should have been rejected (>2 threshold)
- Likely started as simple test, then refined with multiple assertions

## Fix Required

Add validation after RED refinement:

```python
refined_test_code = self._refine_test_to_fail(...)

# ADD: Validate refined test quality
is_valid, quality_feedback = self._validate_test_quality(refined_test_code, increment.test_name)
if not is_valid:
    logger.warning(f"      ⚠️  Refined test has quality issues: {quality_feedback}")
    # Either: reject refinement, or: skip cycle

# Update stored test
test_code = refined_test_code
```

## Additional Bug

Line 1577-1578: Exception handling returns `True` (passes validation):

```python
except Exception as e:
    logger.warning(f"Failed to validate test quality: {e}")
    return True, ""  # ❌ Should fail validation, not pass!
```

Should be:
```python
except Exception as e:
    logger.error(f"Failed to validate test quality: {e}")
    return False, f"Validation failed: {e}"  # ← Fail on error
```