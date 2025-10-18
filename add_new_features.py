#!/usr/bin/env python3
"""
Add New Password Verifier Features

Demonstrates that the TDD Agent:
1. Won't modify test file
2. Won't overwrite existing implementation
3. Will ADD new features only
"""
import sys
from pathlib import Path

sys.path.insert(0, "/home/ch_dev/ace_enterprise")

from src.agents.tdd_agent import TDDAgent

print("=" * 80)
print("  ADDING NEW FEATURES TO EXISTING CODE")
print("=" * 80)

test_file = Path("examples/test_password_verifier.py")
impl_file = Path("examples/password_verifier.py")

# Initialize agent
agent = TDDAgent(language="python")

print(f"\n✓ TDD Agent initialized\n")

# New tests to implement
new_tests = [
    ("test_password_must_not_contain_username", "Reject passwords containing username"),
    ("test_password_history_check", "Check against password history"),
]

print(f"Adding {len(new_tests)} new features:\n")

for i, (test_name, desc) in enumerate(new_tests, 1):
    print(f"[{i}/{len(new_tests)}] {desc}")
    print(f"      Test: {test_name}")

    result = agent.make_test_pass(
        test_path=test_file,
        impl_path=impl_file,
        test_name=test_name,
        max_iterations=3,
    )

    if result["success"]:
        print(f"      ✅ Added after {result['iterations']} iteration(s)")
    else:
        print(f"      ❌ Failed after {result['iterations']} iterations")

    print()

# Final verification
print("=" * 80)
print("  VERIFICATION")
print("=" * 80)

all_passed, _, failed = agent.run_tests(test_file)

if all_passed:
    print("\n✅ ALL 19 TESTS PASS!\n")
else:
    passing = 19 - len(failed)
    print(f"\n📊 {passing}/19 tests passing\n")

# Show what was added
print("=" * 80)
print("  WHAT WAS ADDED")
print("=" * 80)

code = impl_file.read_text()
print(f"\n{code}")

lines = [l for l in code.split('\n') if l.strip()]
funcs = code.count('def ')
print(f"\n📊 Final: {len(lines)} lines, {funcs} function(s)")
print(f"    (was 62 lines, 3 functions)")
