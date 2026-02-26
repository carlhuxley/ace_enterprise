"""Tests for AutonomousTDDAgent module."""
import pytest


class TestTestResult:
    """Tests for TestResult dataclass."""

    def test_all_passed_when_passed_and_no_failures(self):
        """all_passed is True when passed=True and failed_count=0."""
        from src.agents.autonomous_tdd_agent import TestResult

        result = TestResult(passed=True, failed=False, output="OK", test_count=5, failed_count=0)

        assert result.all_passed is True

    def test_all_passed_false_when_failures_exist(self):
        """all_passed is False when there are failures."""
        from src.agents.autonomous_tdd_agent import TestResult

        result = TestResult(passed=True, failed=True, output="FAIL", test_count=5, failed_count=2)

        assert result.all_passed is False


class TestGetLicenseType:
    """Tests for _get_license_type method."""

    def test_openai_raises_error(self):
        """Proprietary providers like OpenAI should raise ValueError."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        with pytest.raises(ValueError, match="Proprietary provider"):
            AutonomousTDDAgent._get_license_type(None, "openai", "gpt-4")

    def test_anthropic_raises_error(self):
        """Proprietary providers like Anthropic should raise ValueError."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        with pytest.raises(ValueError, match="Proprietary provider"):
            AutonomousTDDAgent._get_license_type(None, "anthropic", "claude-3")

    def test_togetherai_llama_returns_open(self):
        """TogetherAI with Llama returns open license."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        license_type = AutonomousTDDAgent._get_license_type(None, "togetherai", "llama-3.1-70b")

        assert "llama" in license_type.lower() or license_type == "open"


class TestExtractMethodFromTestName:
    """Tests for _extract_method_from_test_name method."""

    def test_extracts_method_name(self):
        """Should extract method name from test name."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        result = AutonomousTDDAgent._extract_method_from_test_name(None, "test_add_returns_sum")

        assert result == "add"

    def test_handles_constructor_test(self):
        """Should return __init__ for constructor tests."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        result = AutonomousTDDAgent._extract_method_from_test_name(None, "test_calculator_can_be_created")

        assert result == "__init__"

    def test_handles_no_test_prefix(self):
        """Should return input if no test_ prefix."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        result = AutonomousTDDAgent._extract_method_from_test_name(None, "some_method")

        assert result == "some_method"


class TestCountFunctions:
    """Tests for _count_functions method."""

    def test_counts_single_function(self):
        """Should count one function definition."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        code = "def hello():\n    pass"

        result = AutonomousTDDAgent._count_functions(None, code)

        assert result == 1

    def test_counts_multiple_functions(self):
        """Should count multiple function definitions."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        code = """
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b
"""

        result = AutonomousTDDAgent._count_functions(None, code)

        assert result == 3

    def test_returns_zero_for_invalid_syntax(self):
        """Should return 0 for code with syntax errors."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        code = "def broken(:\n    pass"

        result = AutonomousTDDAgent._count_functions(None, code)

        assert result == 0

    def test_counts_nested_functions(self):
        """Should count nested functions too."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        code = """
def outer():
    def inner():
        pass
    return inner
"""

        result = AutonomousTDDAgent._count_functions(None, code)

        assert result == 2


class TestValidateTestQuality:
    """Tests for _validate_test_quality method."""

    def test_valid_single_assertion(self):
        """Single assertion test should be valid."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        test_code = """
def test_add_returns_sum():
    result = add(2, 3)
    assert result == 5
"""

        is_valid, feedback = AutonomousTDDAgent._validate_test_quality(None, test_code, "test_add_returns_sum")

        assert is_valid is True
        assert feedback == ""

    def test_valid_two_assertions(self):
        """Two assertions is still acceptable."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        test_code = """
def test_user_creation():
    user = create_user("alice")
    assert user is not None
    assert user.name == "alice"
"""

        is_valid, feedback = AutonomousTDDAgent._validate_test_quality(None, test_code, "test_user_creation")

        assert is_valid is True

    def test_invalid_too_many_assertions(self):
        """More than two assertions should be invalid."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        test_code = """
def test_url_contains_all_params():
    url = build_url()
    assert "client_id=" in url
    assert "redirect_uri=" in url
    assert "scope=" in url
    assert "state=" in url
"""

        is_valid, feedback = AutonomousTDDAgent._validate_test_quality(None, test_code, "test_url_contains_all_params")

        assert is_valid is False
        assert "4 assertions" in feedback

    def test_returns_true_if_function_not_found(self):
        """Should return valid if test function not found in code."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        test_code = """
def some_other_function():
    pass
"""

        is_valid, feedback = AutonomousTDDAgent._validate_test_quality(None, test_code, "test_nonexistent")

        assert is_valid is True
