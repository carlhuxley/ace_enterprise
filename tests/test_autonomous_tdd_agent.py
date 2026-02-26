"""Tests for AutonomousTDDAgent module."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

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


# ============================================================================
# Integration Tests - Require file system setup
# ============================================================================

@pytest.fixture
def temp_project():
    """Create a temporary project directory with test and src dirs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        test_dir = project_root / "tests"
        src_dir = project_root / "src"
        test_dir.mkdir()
        src_dir.mkdir()
        yield project_root, test_dir, src_dir


@pytest.fixture
def mock_agent(temp_project):
    """Create a minimal mock agent with required attributes."""
    from src.agents.autonomous_tdd_agent import AutonomousTDDAgent
    from src.agents.redundancy_checker import RedundancyPreChecker

    project_root, test_dir, src_dir = temp_project

    # Create a mock agent by setting attributes directly
    agent = MagicMock(spec=AutonomousTDDAgent)
    agent.project_root = project_root
    agent.test_dir = test_dir
    agent.src_dir = src_dir
    agent.test_functions = {}
    agent.redundancy_checker = RedundancyPreChecker()

    return agent


class TestRunTestsIntegration:
    """Integration tests for _run_tests method."""

    def test_run_tests_with_passing_test(self, temp_project):
        """Should return passed=True for passing test."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        project_root, test_dir, src_dir = temp_project

        # Write a simple passing test
        test_file = test_dir / "test_simple.py"
        test_file.write_text("""
def test_always_passes():
    assert 1 + 1 == 2
""")

        # Create minimal agent mock
        agent = MagicMock()
        agent.project_root = project_root
        agent.test_dir = test_dir

        # Call the actual method
        result = AutonomousTDDAgent._run_tests(agent)

        assert result.passed is True
        assert result.failed is False
        assert result.test_count >= 1
        assert result.failed_count == 0

    def test_run_tests_with_failing_test(self, temp_project):
        """Should return passed=False for failing test."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        project_root, test_dir, src_dir = temp_project

        # Write a failing test
        test_file = test_dir / "test_fail.py"
        test_file.write_text("""
def test_always_fails():
    assert 1 == 2, "Expected failure"
""")

        agent = MagicMock()
        agent.project_root = project_root
        agent.test_dir = test_dir

        result = AutonomousTDDAgent._run_tests(agent)

        assert result.passed is False
        assert result.failed is True
        assert result.failed_count >= 1

    def test_run_tests_counts_multiple_tests(self, temp_project):
        """Should count multiple tests correctly."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        project_root, test_dir, src_dir = temp_project

        test_file = test_dir / "test_multiple.py"
        test_file.write_text("""
def test_one():
    assert True

def test_two():
    assert True

def test_three():
    assert True
""")

        agent = MagicMock()
        agent.project_root = project_root
        agent.test_dir = test_dir

        result = AutonomousTDDAgent._run_tests(agent)

        assert result.passed is True
        assert result.test_count == 3


class TestBuildExistingTestsList:
    """Integration tests for _build_existing_tests_list method."""

    def test_builds_list_from_test_functions(self):
        """Should build ExistingTest list from test_functions dict."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        agent = MagicMock()
        agent.test_functions = {
            "tests/test_calc.py": [
                {
                    "cycle": 1,
                    "name": "test_add_returns_sum",
                    "code": "def test_add_returns_sum():\n    assert add(2, 3) == 5"
                },
                {
                    "cycle": 2,
                    "name": "test_subtract_returns_difference",
                    "code": "def test_subtract_returns_difference():\n    assert subtract(5, 3) == 2"
                }
            ]
        }

        result = AutonomousTDDAgent._build_existing_tests_list(agent)

        assert len(result) == 2
        assert result[0].name == "test_add_returns_sum"
        assert result[0].file_path == "tests/test_calc.py"
        assert "assert add(2, 3) == 5" in result[0].assertions[0]

    def test_empty_when_no_test_functions(self):
        """Should return empty list when no tests exist."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        agent = MagicMock()
        agent.test_functions = {}

        result = AutonomousTDDAgent._build_existing_tests_list(agent)

        assert result == []

    def test_extracts_assertions_from_code(self):
        """Should extract assert lines from test code."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        agent = MagicMock()
        agent.test_functions = {
            "tests/test_user.py": [
                {
                    "cycle": 1,
                    "name": "test_user_has_name",
                    "code": """def test_user_has_name():
    user = User("alice")
    assert user.name == "alice"
    assert user is not None"""
                }
            ]
        }

        result = AutonomousTDDAgent._build_existing_tests_list(agent)

        assert len(result[0].assertions) == 2
        assert 'assert user.name == "alice"' in result[0].assertions[0]


class TestNeedsRefactoring:
    """Tests for _needs_refactoring method (currently stub)."""

    def test_always_returns_false(self):
        """Currently returns False (Phase 3 feature)."""
        from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

        result = AutonomousTDDAgent._needs_refactoring(None, "def foo(): pass")

        assert result is False
