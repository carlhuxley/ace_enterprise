# TDD Playbook Design

## Overview

The TDD playbook is **language-agnostic** and focuses on Test-Driven Development patterns, principles, and anti-patterns that apply across all programming languages.

## Playbook Structure

### Domain: `tdd_general`

This playbook captures cross-language TDD knowledge that can be applied to Python, TypeScript, Go, and other languages as pods are added.

---

## Section: `strategies_and_hard_rules`

TDD principles and workflows that must be followed.

**Example Bullets:**

1. **Red-Green-Refactor Cycle**
   - Always write the failing test first (RED)
   - Write minimal code to make it pass (GREEN)
   - Refactor only after tests pass (REFACTOR)
   - Tags: `core_principle`, `workflow`

2. **One Test at a Time**
   - Focus on making one failing test pass before moving to the next
   - Avoid writing multiple failing tests simultaneously
   - This prevents overwhelm and maintains focus
   - Tags: `workflow`, `focus`

3. **Test Isolation**
   - Each test should be independent and runnable in any order
   - Tests should not depend on state from other tests
   - Use setup/teardown or fixtures for test data
   - Tags: `best_practice`, `test_design`

4. **Minimal Implementation**
   - Write only enough code to make the current test pass
   - Resist the urge to add "future" functionality
   - Let failing tests drive what code to write next
   - Tags: `best_practice`, `discipline`

5. **Test Names Should Be Descriptive**
   - Test names should describe what behavior is being tested
   - Good: `test_add_returns_sum_of_two_positive_numbers`
   - Bad: `test_add`, `test1`
   - Tags: `naming`, `clarity`

---

## Section: `code_snippets`

Language-specific snippets showing TDD patterns.

**Example Bullets:**

### Python

1. **Basic Test Structure (pytest)**
   ```python
   def test_function_does_expected_behavior():
       # Arrange - set up test data
       input_value = 5

       # Act - call the function
       result = my_function(input_value)

       # Assert - verify behavior
       assert result == expected_value
   ```
   - Tags: `python`, `pytest`, `pattern_AAA`

2. **Testing Exceptions (pytest)**
   ```python
   import pytest

   def test_function_raises_error_on_invalid_input():
       with pytest.raises(ValueError, match="error message"):
           function_that_should_fail(invalid_input)
   ```
   - Tags: `python`, `pytest`, `exceptions`

3. **Using Fixtures for Test Data (pytest)**
   ```python
   @pytest.fixture
   def sample_data():
       return {"key": "value"}

   def test_with_fixture(sample_data):
       assert sample_data["key"] == "value"
   ```
   - Tags: `python`, `pytest`, `fixtures`

### JavaScript

4. **Basic Test Structure (Jest)**
   ```javascript
   test('function does expected behavior', () => {
       // Arrange
       const inputValue = 5;

       // Act
       const result = myFunction(inputValue);

       // Assert
       expect(result).toBe(expectedValue);
   });
   ```
   - Tags: `javascript`, `jest`, `pattern_AAA`

5. **Testing Exceptions (Jest)**
   ```javascript
   test('function throws error on invalid input', () => {
       expect(() => {
           functionThatShouldFail(invalidInput);
       }).toThrow('error message');
   });
   ```
   - Tags: `javascript`, `jest`, `exceptions`

---

## Section: `troubleshooting`

Common TDD problems and their solutions.

**Example Bullets:**

1. **Problem: Test Passes Immediately Without Implementation**
   - Cause: Test is too weak or not actually testing the behavior
   - Solution: Verify test fails first (RED step), then implement
   - Check that assertions are actually checking the right thing
   - Tags: `weak_tests`, `debugging`

2. **Problem: Tests Are Brittle and Break Often**
   - Cause: Tests are too coupled to implementation details
   - Solution: Test behavior/contracts, not implementation
   - Avoid testing private methods; focus on public API
   - Use mocks/stubs sparingly; prefer real dependencies when possible
   - Tags: `test_maintenance`, `coupling`

3. **Problem: Can't Make Test Pass Without Big Changes**
   - Cause: Test is too ambitious; trying to test too much at once
   - Solution: Break down into smaller, incremental tests
   - Use triangulation: add more specific test cases to drive design
   - Tags: `test_granularity`, `incremental`

4. **Problem: Don't Know What to Test Next**
   - Solution: Use the transformation priority premise
   - Start with simplest cases (constants, simple returns)
   - Gradually add complexity (conditionals, loops, data structures)
   - Let the current implementation guide what edge case to test next
   - Tags: `test_ordering`, `strategy`

5. **Problem: Failing Test Requires Implementation That Doesn't Exist**
   - Cause: Missing module, class, or function
   - Solution: Create minimal stub/skeleton first
   - Define function/class signature with placeholder return/behavior
   - Then write test for that stub, make it pass, iterate
   - Tags: `bootstrapping`, `workflow`

---

## Section: `domain_knowledge`

Deep TDD concepts and theory.

**Example Bullets:**

1. **Transformation Priority Premise**
   - Transformations are ordered from simple to complex:
     1. `{}→nil` (no code at all → code that returns nil/null)
     2. `nil→constant` (return constant value)
     3. `constant→variable` (use a variable instead of constant)
     4. `unconditional→if` (add conditional logic)
     5. `scalar→array` (return array/collection)
     6. `array→container` (use proper data structures)
     7. `statement→recursion` (add recursive logic)
     8. `if→while` (add loops)
     9. And more complex transformations...
   - Use simpler transformations before complex ones
   - Tags: `theory`, `uncle_bob`, `incremental`

2. **Triangulation Technique**
   - When unsure how to implement, add more test cases
   - Multiple examples help reveal the general solution
   - Example: Testing `add(2, 3) == 5` alone might lead to `return 5`
   - Adding `add(1, 1) == 2` forces proper implementation
   - Tags: `technique`, `test_design`

3. **The Three Laws of TDD (Uncle Bob)**
   - Law 1: Don't write production code until you have a failing test
   - Law 2: Don't write more of a test than is sufficient to fail
   - Law 3: Don't write more production code than is sufficient to pass
   - Tags: `principles`, `uncle_bob`, `discipline`

4. **Test Smells to Avoid**
   - **Mystery Guest**: Test depends on external data not visible in test
   - **Resource Optimism**: Test assumes resources (files, DB) are available
   - **Test Interdependence**: Tests must run in specific order
   - **Assertion Roulette**: Multiple assertions without clear messages
   - **Slow Tests**: Tests that take too long discourage running them
   - Tags: `anti_patterns`, `code_smells`

5. **Test Doubles: Mocks vs Stubs vs Fakes**
   - **Stub**: Provides canned answers to calls (simple replacement)
   - **Mock**: Verifies interactions happened (assertion on calls)
   - **Fake**: Working implementation, but simplified (e.g., in-memory DB)
   - **Spy**: Records information about how it was called
   - Use the simplest type that works for your test
   - Tags: `testing_patterns`, `terminology`

6. **When NOT to Use TDD**
   - Exploratory/spike code where requirements are very unclear
   - Purely visual/UI work where feedback is better from seeing it
   - Prototypes that will be thrown away
   - Code that's heavily algorithm-research based
   - Even then, tests are valuable; just don't let them slow exploration
   - Tags: `pragmatism`, `context`

---

## Language-Specific Playbooks

While the TDD principles are universal, each language has its own ecosystem:

### `tdd_python`
- pytest-specific patterns
- unittest patterns
- Mock/patch techniques (unittest.mock)
- Python-specific test organization

### `tdd_javascript`
- Jest patterns
- Mocha/Chai patterns
- Testing async code (promises, async/await)
- React Testing Library patterns

### `tdd_go`
- Go testing package patterns
- Table-driven tests
- Testify assertions
- Mock generation

---

## How ACE Uses TDD Playbooks

1. **Generator receives task**: "Make test_add_two_numbers pass"

2. **Playbook retrieval**:
   - Searches `tdd_general` for universal TDD wisdom
   - Searches `tdd_python` for language-specific patterns
   - Combines relevant bullets

3. **Code generation**:
   - Follows minimal implementation principle
   - Uses language-specific test patterns
   - Applies relevant troubleshooting knowledge

4. **Reflection on failure**:
   - Identifies which TDD principle was violated
   - Analyzes test failure patterns
   - Recommends specific transformations

5. **Curation**:
   - Adds new language-specific patterns discovered
   - Records anti-patterns encountered
   - Builds domain expertise over time

---

## Benefits of This Design

✅ **Language-agnostic core**: TDD principles apply everywhere
✅ **Language-specific extensions**: Practical patterns for each ecosystem
✅ **Incremental learning**: ACE builds expertise across languages
✅ **Reusable knowledge**: Python TDD failures inform JavaScript work
✅ **Production-ready**: Matches how real developers work with TDD

---

## Next Steps

1. ✅ Prove single test can pass
2. ⏳ Build TDD agent that:
   - Reads failing tests
   - Applies TDD playbook knowledge
   - Generates minimal implementation
   - Learns from failures across iterations
3. ⏳ Test with multi-test scenarios
4. ⏳ Add support for different languages
