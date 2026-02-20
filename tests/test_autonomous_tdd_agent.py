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
