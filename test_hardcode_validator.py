#!/usr/bin/env python3
"""
Quick test for the hardcode implementation validator.
"""
import ast

def validate_hardcode_implementation(impl_code: str, method_name: str) -> tuple[bool, str]:
    """
    Simplified version of the validator for testing.
    This is a copy of the logic from AutonomousTDDAgent._validate_hardcode_implementation
    """
    try:
        tree = ast.parse(impl_code)

        # Find the method being implemented
        target_func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == method_name:
                target_func = node
                break

        if not target_func:
            return True, ""  # Can't find function, skip validation

        # Check for FORBIDDEN patterns
        violations = []

        for node in ast.walk(target_func):
            # F-strings (JoinedStr)
            if isinstance(node, ast.JoinedStr):
                violations.append("f-string formatting (f\"...\")")

            # .format() calls
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == 'format':
                    violations.append(".format() method")
                # urlencode, quote, etc.
                if isinstance(node.func, ast.Name):
                    if node.func.id in ['urlencode', 'quote', 'quote_plus', 'dumps', 'loads']:
                        violations.append(f"{node.func.id}() library call")
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr in ['urlencode', 'quote', 'quote_plus', 'dumps', 'loads', 'encode', 'decode']:
                        violations.append(f".{node.func.attr}() method")

            # Loops
            elif isinstance(node, (ast.For, ast.While)):
                violations.append("loop (for/while)")

            # Comprehensions
            elif isinstance(node, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
                violations.append("comprehension")

            # Lambda functions
            elif isinstance(node, ast.Lambda):
                violations.append("lambda function")

            # If/else (allow simple if for minimal logic, but flag complex ones)
            elif isinstance(node, ast.If):
                # Count nested ifs - complex logic
                if any(isinstance(n, ast.If) for n in ast.walk(node)):
                    violations.append("nested if/else (complex logic)")

        if violations:
            feedback = f"HARDCODE violations: {', '.join(violations)}"
            return False, feedback

        return True, ""

    except Exception as e:
        return True, ""  # Skip validation on error

def test_validator():
    """Test the _validate_hardcode_implementation method."""

    # Test 1: Hardcoded implementation (VALID)
    valid_code = '''
def generate_authorization_url(self):
    return "https://auth.example.com?client_id=test&redirect_uri=http%3A%2F%2Fcallback"
'''
    is_valid, feedback = validate_hardcode_implementation(valid_code, "generate_authorization_url")
    print(f"Test 1 - Hardcoded literal (should be VALID): {is_valid}")
    if not is_valid:
        print(f"  UNEXPECTED FAILURE: {feedback[:200]}")
    else:
        print("  ✓ PASSED")

    # Test 2: F-string implementation (INVALID)
    invalid_fstring = '''
def generate_authorization_url(self):
    return f"https://auth.example.com?client_id={self.client_id}&redirect_uri=http%3A%2F%2Fcallback"
'''
    is_valid, feedback = validate_hardcode_implementation(invalid_fstring, "generate_authorization_url")
    print(f"\nTest 2 - F-string (should be INVALID): {is_valid}")
    if is_valid:
        print(f"  UNEXPECTED PASS - should have caught f-string!")
    else:
        print("  ✓ PASSED - Caught f-string violation")
        print(f"  Feedback snippet: {feedback[:150]}...")

    # Test 3: .format() implementation (INVALID)
    invalid_format = '''
def generate_authorization_url(self):
    return "https://auth.example.com?client_id={}".format(self.client_id)
'''
    is_valid, feedback = validate_hardcode_implementation(invalid_format, "generate_authorization_url")
    print(f"\nTest 3 - .format() (should be INVALID): {is_valid}")
    if is_valid:
        print(f"  UNEXPECTED PASS - should have caught .format()!")
    else:
        print("  ✓ PASSED - Caught .format() violation")
        print(f"  Feedback snippet: {feedback[:150]}...")

    # Test 4: Loop implementation (INVALID)
    invalid_loop = '''
def validate_token(self, token):
    results = []
    for claim in ["sub", "exp", "iat"]:
        results.append(claim)
    return results
'''
    is_valid, feedback = validate_hardcode_implementation(invalid_loop, "validate_token")
    print(f"\nTest 4 - Loop (should be INVALID): {is_valid}")
    if is_valid:
        print(f"  UNEXPECTED PASS - should have caught loop!")
    else:
        print("  ✓ PASSED - Caught loop violation")
        print(f"  Feedback snippet: {feedback[:150]}...")

    # Test 5: Comprehension (INVALID)
    invalid_comp = '''
def get_claims(self):
    return {k: v for k, v in [("sub", "user123"), ("exp", 123456)]}
'''
    is_valid, feedback = validate_hardcode_implementation(invalid_comp, "get_claims")
    print(f"\nTest 5 - Comprehension (should be INVALID): {is_valid}")
    if is_valid:
        print(f"  UNEXPECTED PASS - should have caught comprehension!")
    else:
        print("  ✓ PASSED - Caught comprehension violation")
        print(f"  Feedback snippet: {feedback[:150]}...")

    print("\n" + "="*60)
    print("Validator test complete!")

if __name__ == "__main__":
    test_validator()
