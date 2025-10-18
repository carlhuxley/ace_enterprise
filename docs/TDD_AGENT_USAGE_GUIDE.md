# TDD Agent Usage Guide

## Quick Start

### Installation

```bash
# Clone the repo
git clone <repo-url>
cd ace_enterprise

# Install dependencies
pip install -r requirements.txt

# Set up your LLM provider (OpenAI, Anthropic, or Ollama)
export OPENAI_API_KEY="your-key"
# or
export ANTHROPIC_API_KEY="your-key"
# or run Ollama locally
```

### Basic Usage

```python
from pathlib import Path
from src.agents.tdd_agent import TDDAgent

# Initialize agent
agent = TDDAgent(language="python")

# Make a specific test pass
result = agent.make_test_pass(
    test_path=Path("tests/test_my_module.py"),
    impl_path=Path("src/my_module.py"),
    test_name="test_my_function",
    max_iterations=3,
)

if result["success"]:
    print(f"✅ Test passed after {result['iterations']} iteration(s)!")
else:
    print(f"❌ Failed to make test pass")
    print(result["final_output"])
```

---

## Use Cases

### 1. Make a Single Test Pass

**Scenario**: You have a failing test and want ACE to implement it.

```python
from pathlib import Path
from src.agents.tdd_agent import TDDAgent

agent = TDDAgent(language="python")

result = agent.make_test_pass(
    test_path=Path("tests/test_auth.py"),
    impl_path=Path("src/auth.py"),
    test_name="test_login_with_valid_credentials",
    max_iterations=3,
)

print(f"Success: {result['success']}")
print(f"Iterations: {result['iterations']}")
print(f"Learned: {result['bullets_added']} new patterns")
```

**Output**:
```
Success: True
Iterations: 1
Learned: 0 new patterns
```

---

### 2. Implement Multiple Tests Incrementally

**Scenario**: You have multiple tests and want to pass them one at a time (TDD workflow).

```python
from pathlib import Path
from src.agents.tdd_agent import TDDAgent

agent = TDDAgent(language="python")

test_file = Path("tests/test_calculator.py")
impl_file = Path("src/calculator.py")

# Define test sequence
tests = [
    "test_add",
    "test_subtract",
    "test_multiply",
    "test_divide",
]

# Pass each test incrementally
for test_name in tests:
    print(f"\n🎯 Making {test_name} pass...")

    result = agent.make_test_pass(
        test_path=test_file,
        impl_path=impl_file,
        test_name=test_name,
        max_iterations=3,
    )

    if result["success"]:
        print(f"  ✅ Passed after {result['iterations']} iteration(s)")
    else:
        print(f"  ❌ Failed")
        break

# Verify all tests pass
passed, output, failed = agent.run_tests(test_file)
print(f"\n{'✅' if passed else '❌'} Final result: {len(tests) - len(failed)}/{len(tests)} tests passing")
```

**Output**:
```
🎯 Making test_add pass...
  ✅ Passed after 1 iteration(s)

🎯 Making test_subtract pass...
  ✅ Passed after 1 iteration(s)

🎯 Making test_multiply pass...
  ✅ Passed after 1 iteration(s)

🎯 Making test_divide pass...
  ✅ Passed after 2 iteration(s)

✅ Final result: 4/4 tests passing
```

---

### 3. Make All Tests in a File Pass

**Scenario**: You have a test file with multiple tests and want to pass them all at once.

```python
from pathlib import Path
from src.agents.tdd_agent import TDDAgent

agent = TDDAgent(language="python")

result = agent.make_test_pass(
    test_path=Path("tests/test_utils.py"),
    impl_path=Path("src/utils.py"),
    test_name=None,  # None = all tests
    max_iterations=5,
)

if result["success"]:
    print(f"✅ All tests passed!")
else:
    print(f"❌ Some tests still failing after {result['iterations']} iterations")
```

---

### 4. Use with Existing Playbook

**Scenario**: You have an existing TDD playbook with learned patterns and want to use it.

```python
from src.agents.tdd_agent import TDDAgent
from src.playbook.manager import PlaybookManager

# Load existing playbook
manager = PlaybookManager()
playbook_id = "pb_tdd_python_20251018_123"  # Your existing playbook

# Create agent with existing playbook
agent = TDDAgent(
    playbook_manager=manager,
    playbook_id=playbook_id,
    language="python",
)

# Agent will use learned patterns from the playbook
result = agent.make_test_pass(
    test_path=Path("tests/test_new_feature.py"),
    impl_path=Path("src/new_feature.py"),
    test_name="test_feature_works",
)
```

---

### 5. Track Learning Over Time

**Scenario**: You want to see how the playbook grows as the agent learns.

```python
from pathlib import Path
from src.agents.tdd_agent import TDDAgent

agent = TDDAgent(language="python")

# Check initial state
initial_stats = agent.get_playbook_stats()
print(f"Initial bullets: {initial_stats['total_bullets']}")

# Run multiple test implementations
test_files = [
    ("tests/test_auth.py", "src/auth.py"),
    ("tests/test_api.py", "src/api.py"),
    ("tests/test_db.py", "src/db.py"),
]

total_learned = 0

for test_path, impl_path in test_files:
    result = agent.make_test_pass(
        test_path=Path(test_path),
        impl_path=Path(impl_path),
        max_iterations=3,
    )

    total_learned += result["bullets_added"]

    if result["bullets_added"] > 0:
        print(f"📚 Learned {result['bullets_added']} patterns from {test_path}")

# Check final state
final_stats = agent.get_playbook_stats()
print(f"\n📊 Learning Summary:")
print(f"  Initial bullets: {initial_stats['total_bullets']}")
print(f"  Final bullets: {final_stats['total_bullets']}")
print(f"  Total learned: {total_learned}")
```

**Output**:
```
Initial bullets: 0

📚 Learned 2 patterns from tests/test_auth.py
📚 Learned 1 patterns from tests/test_db.py

📊 Learning Summary:
  Initial bullets: 0
  Final bullets: 3
  Total learned: 3
```

---

### 6. Custom LLM Configuration

**Scenario**: You want to use a specific LLM model or provider.

```python
from src.agents.tdd_agent import TDDAgent
from src.utils.llm_client import LLMClient

# Option 1: Use specific provider
llm = LLMClient(provider="anthropic", model="claude-3-5-sonnet-20241022")
agent = TDDAgent(llm_client=llm, language="python")

# Option 2: Use local Ollama
llm = LLMClient(provider="ollama", model="qwen2.5-coder:7b")
agent = TDDAgent(llm_client=llm, language="python")

# Option 3: Use OpenAI
llm = LLMClient(provider="openai", model="gpt-4-turbo-preview")
agent = TDDAgent(llm_client=llm, language="python")

# Then use agent normally
result = agent.make_test_pass(...)
```

---

## Advanced Patterns

### Pattern 1: Implement Feature with Multiple Tests

Create a script that implements an entire feature:

```python
#!/usr/bin/env python3
"""Implement user authentication feature using TDD."""
from pathlib import Path
from src.agents.tdd_agent import TDDAgent

def implement_auth_feature():
    agent = TDDAgent(language="python")

    test_file = Path("tests/test_auth.py")
    impl_file = Path("src/auth.py")

    # Feature broken into incremental tests
    auth_tests = [
        "test_create_user",
        "test_user_password_is_hashed",
        "test_login_with_valid_credentials",
        "test_login_with_invalid_credentials",
        "test_login_with_nonexistent_user",
        "test_logout_invalidates_session",
        "test_password_reset_generates_token",
        "test_password_reset_with_valid_token",
    ]

    for i, test in enumerate(auth_tests, 1):
        print(f"\n[{i}/{len(auth_tests)}] Implementing: {test}")

        result = agent.make_test_pass(
            test_path=test_file,
            impl_path=impl_file,
            test_name=test,
            max_iterations=3,
        )

        if not result["success"]:
            print(f"❌ Failed on {test}")
            return False

    # Verify all tests pass
    passed, _, _ = agent.run_tests(test_file)

    if passed:
        print("\n✅ Auth feature fully implemented!")
        print(f"📄 Implementation: {impl_file}")

        # Show playbook growth
        stats = agent.get_playbook_stats()
        print(f"📚 Playbook bullets: {stats['total_bullets']}")
        return True
    else:
        print("\n❌ Some tests still failing")
        return False

if __name__ == "__main__":
    implement_auth_feature()
```

---

### Pattern 2: TDD Agent as Pre-commit Hook

Automatically implement code for failing tests before commit:

```python
#!/usr/bin/env python3
"""Pre-commit hook: Auto-implement failing tests."""
import sys
from pathlib import Path
from src.agents.tdd_agent import TDDAgent

def pre_commit_hook():
    """Run TDD agent on any failing tests."""
    agent = TDDAgent(language="python")

    # Find all test files
    test_dir = Path("tests")
    test_files = list(test_dir.glob("test_*.py"))

    for test_file in test_files:
        # Run tests to find failures
        passed, output, failed_tests = agent.run_tests(test_file)

        if not passed and failed_tests:
            print(f"🔧 Found {len(failed_tests)} failing tests in {test_file}")

            # Try to implement each failing test
            for failed in failed_tests:
                # Extract test name from "test_file.py::test_name"
                test_name = failed.split("::")[-1]

                # Guess implementation path from test path
                # tests/test_auth.py -> src/auth.py
                impl_file = Path("src") / test_file.stem.replace("test_", "") + ".py"

                print(f"  Attempting to implement: {test_name}")

                result = agent.make_test_pass(
                    test_path=test_file,
                    impl_path=impl_file,
                    test_name=test_name,
                    max_iterations=2,
                )

                if result["success"]:
                    print(f"    ✅ Implemented successfully")
                else:
                    print(f"    ❌ Could not implement automatically")
                    print(f"    Please implement manually: {test_name}")
                    return 1  # Block commit

    print("✅ All tests passing")
    return 0

if __name__ == "__main__":
    sys.exit(pre_commit_hook())
```

---

### Pattern 3: Generate Implementation from Specification

Use TDD agent to generate code from natural language specs:

```python
#!/usr/bin/env python3
"""Generate implementation from specification."""
from pathlib import Path
from src.agents.tdd_agent import TDDAgent

def generate_from_spec(spec_text: str, output_file: Path):
    """
    Generate implementation from specification.

    Steps:
    1. Generate tests from spec (using LLM)
    2. Use TDD agent to implement tests
    3. Return implementation
    """
    # First, generate tests from spec
    # (This would use Generator to create tests)

    # Then use TDD agent to implement
    agent = TDDAgent(language="python")

    test_file = Path("tests/test_generated.py")

    # Assume tests are generated here...
    # write_tests(spec_text, test_file)

    result = agent.make_test_pass(
        test_path=test_file,
        impl_path=output_file,
        max_iterations=5,
    )

    return result["success"]

# Example usage
spec = """
Create a function that validates email addresses.
- Valid emails have @ symbol
- Domain must have at least one dot
- No spaces allowed
- Returns True if valid, False otherwise
"""

success = generate_from_spec(spec, Path("src/email_validator.py"))
```

---

## Best Practices

### 1. Start with Simple Tests

Begin with the simplest possible test:

```python
# Good: Simple, focused test
def test_add_returns_sum():
    assert add(2, 3) == 5

# Avoid: Complex test with many assertions
def test_calculator_full_functionality():
    assert add(2, 3) == 5
    assert subtract(5, 3) == 2
    assert multiply(2, 3) == 6
    # ... many more
```

The agent works best when tests are small and focused.

---

### 2. Use Descriptive Test Names

```python
# Good: Descriptive name
def test_divide_by_zero_raises_value_error():
    with pytest.raises(ValueError):
        divide(5, 0)

# Avoid: Generic name
def test_divide_error():
    with pytest.raises(ValueError):
        divide(5, 0)
```

Descriptive names help the agent understand what to implement.

---

### 3. One Behavior Per Test

```python
# Good: Tests one specific behavior
def test_login_with_valid_credentials_returns_token():
    token = login("user", "correct_password")
    assert isinstance(token, str)
    assert len(token) > 0

# Avoid: Tests multiple behaviors
def test_login():
    # Valid login
    token = login("user", "correct_password")
    assert token

    # Invalid login
    with pytest.raises(AuthError):
        login("user", "wrong_password")

    # Missing user
    with pytest.raises(UserNotFound):
        login("nobody", "password")
```

Single-behavior tests are easier for the agent to understand and implement.

---

### 4. Let Tests Drive Design

Don't write implementation first. Let the agent discover the design through tests:

```python
# Write tests that describe the API you want
def test_user_repository_saves_user():
    repo = UserRepository()
    user = User(name="Alice")
    saved_user = repo.save(user)
    assert saved_user.id is not None

# Agent will generate appropriate design based on test
```

---

### 5. Iterate on Failures

If the agent can't pass a test, the failure often reveals the test is too ambitious:

```python
# If this fails:
def test_full_authentication_flow():
    # Many steps...
    pass

# Break it down:
def test_create_user():
    pass

def test_hash_password():
    pass

def test_verify_password():
    pass

def test_generate_session_token():
    pass
```

---

## Troubleshooting

### Problem: Agent overwrites existing functions

**Solution**: This was fixed in the latest version. Make sure you're using the updated `TDDAgent` that preserves existing code.

If you're still seeing this:
- Check that `impl_path` points to the correct file
- Verify the agent is reading existing code (check logs)
- File an issue with reproduction steps

---

### Problem: Tests pass individually but fail together

**Cause**: Tests may have hidden dependencies or shared state.

**Solution**: Ensure test isolation:
```python
@pytest.fixture
def clean_database():
    db = Database()
    yield db
    db.clear()  # Clean up after test

def test_create_user(clean_database):
    # Test uses isolated database
    pass
```

---

### Problem: Agent can't make complex test pass

**Cause**: Test may be too ambitious for current implementation.

**Solution**: Break down into smaller tests using triangulation:
```python
# Instead of this complex test:
def test_fibonacci_sequence():
    assert fib(0) == 0
    assert fib(1) == 1
    assert fib(10) == 55

# Try incremental tests:
def test_fibonacci_base_case_zero():
    assert fib(0) == 0

def test_fibonacci_base_case_one():
    assert fib(1) == 1

def test_fibonacci_recursive_case():
    assert fib(2) == 1
    assert fib(3) == 2
```

---

### Problem: Agent learns wrong patterns

**Cause**: Bad implementation got added to playbook.

**Solution**:
1. Review playbook bullets (see Playbook Manager docs)
2. Mark unhelpful bullets as "harmful"
3. Or start with fresh playbook

```python
from src.playbook.manager import PlaybookManager

manager = PlaybookManager()

# Get playbook
playbook = manager.get_playbook("pb_id_here")

# Review bullets
for section, bullets in playbook.sections.items():
    for bullet in bullets:
        print(f"{bullet.id}: {bullet.content}")
        print(f"  Helpful: {bullet.helpful_count}, Harmful: {bullet.harmful_count}")
```

---

## Next Steps

- **Try the demos**: Run `python demo_tdd_single_test.py` and `python demo_tdd_agent.py`
- **Read the design doc**: See `docs/TDD_PLAYBOOK_DESIGN.md` for playbook structure
- **Extend for your language**: Add support for JavaScript, Java, etc.
- **Build your own agent**: Use `TDDAgent` as a component in larger workflows

---

## Support

For issues, questions, or contributions:
- Check the documentation in `docs/`
- Review example demos in the root directory
- File issues on GitHub
- Read the ACE paper for theoretical background
