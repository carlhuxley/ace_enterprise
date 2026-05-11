"""Tests for GherkinFeatureBridge and PolyglotTDDRunner.run_from_feature (ace_enterprise-0tt)."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.agents.gherkin_feature_bridge import FeatureSpec, GherkinFeatureBridge, ScenarioSpec
from src.agents.language_pod import TokenUsage
from src.analytics.token_efficiency import EfficiencyReport


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_feature(tmp_path, content: str) -> Path:
    p = tmp_path / "test.feature"
    p.write_text(content)
    return p


SIMPLE_FEATURE = """\
Feature: User authentication with JWT
  As a user
  I want to log in with a JWT token
  So that I can access protected resources

  Scenario: Successful login
    Given a valid username and password
    When I submit the login form
    Then I receive a JWT token
    And I am redirected to the dashboard
"""

MULTI_SCENARIO_FEATURE = """\
Feature: Order processing
  Scenario: Place a new order
    Given a customer with a valid cart
    When the customer checks out
    Then an order is created

  Scenario: Cancel an order
    Given an existing order
    When the customer cancels
    Then the order status is cancelled
    And a refund is issued
"""

NO_FEATURE_LINE = """\
  Scenario: Something
    Given a thing
    When I do it
    Then it works
"""

EMPTY_SCENARIOS_FEATURE = """\
Feature: A minimal feature with no scenarios
"""


# ---------------------------------------------------------------------------
# FeatureSpec schema
# ---------------------------------------------------------------------------

class TestFeatureSpec:
    def test_title_field(self):
        spec = FeatureSpec(title="Auth feature", scenarios=[])
        assert spec.title == "Auth feature"

    def test_scenarios_field(self):
        s = ScenarioSpec(name="Login", steps=["Given x", "When y", "Then z"])
        spec = FeatureSpec(title="Auth", scenarios=[s])
        assert len(spec.scenarios) == 1

    def test_as_requirement_returns_title_when_no_scenarios(self):
        spec = FeatureSpec(title="Auth feature", scenarios=[])
        assert spec.as_requirement() == "Auth feature"

    def test_as_requirement_includes_title(self, tmp_path):
        p = _write_feature(tmp_path, SIMPLE_FEATURE)
        spec = GherkinFeatureBridge.parse(p)
        assert "User authentication with JWT" in spec.as_requirement()

    def test_as_requirement_includes_scenario_names(self, tmp_path):
        p = _write_feature(tmp_path, MULTI_SCENARIO_FEATURE)
        spec = GherkinFeatureBridge.parse(p)
        req = spec.as_requirement()
        assert "Place a new order" in req
        assert "Cancel an order" in req

    def test_as_requirement_includes_step_counts(self, tmp_path):
        p = _write_feature(tmp_path, SIMPLE_FEATURE)
        spec = GherkinFeatureBridge.parse(p)
        req = spec.as_requirement()
        assert "4 steps" in req


# ---------------------------------------------------------------------------
# GherkinFeatureBridge.parse
# ---------------------------------------------------------------------------

class TestGherkinFeatureBridgeParse:
    def test_returns_feature_spec(self, tmp_path):
        p = _write_feature(tmp_path, SIMPLE_FEATURE)
        result = GherkinFeatureBridge.parse(p)
        assert isinstance(result, FeatureSpec)

    def test_extracts_feature_title(self, tmp_path):
        p = _write_feature(tmp_path, SIMPLE_FEATURE)
        spec = GherkinFeatureBridge.parse(p)
        assert spec.title == "User authentication with JWT"

    def test_missing_feature_line_raises_value_error(self, tmp_path):
        p = _write_feature(tmp_path, NO_FEATURE_LINE)
        with pytest.raises(ValueError, match="Feature"):
            GherkinFeatureBridge.parse(p)

    def test_single_scenario_parsed(self, tmp_path):
        p = _write_feature(tmp_path, SIMPLE_FEATURE)
        spec = GherkinFeatureBridge.parse(p)
        assert len(spec.scenarios) == 1

    def test_multiple_scenarios_parsed(self, tmp_path):
        p = _write_feature(tmp_path, MULTI_SCENARIO_FEATURE)
        spec = GherkinFeatureBridge.parse(p)
        assert len(spec.scenarios) == 2

    def test_scenario_names_extracted(self, tmp_path):
        p = _write_feature(tmp_path, MULTI_SCENARIO_FEATURE)
        spec = GherkinFeatureBridge.parse(p)
        names = [s.name for s in spec.scenarios]
        assert "Place a new order" in names
        assert "Cancel an order" in names

    def test_step_count_per_scenario(self, tmp_path):
        p = _write_feature(tmp_path, MULTI_SCENARIO_FEATURE)
        spec = GherkinFeatureBridge.parse(p)
        by_name = {s.name: s for s in spec.scenarios}
        assert len(by_name["Place a new order"].steps) == 3
        assert len(by_name["Cancel an order"].steps) == 4

    def test_no_scenarios_is_valid(self, tmp_path):
        p = _write_feature(tmp_path, EMPTY_SCENARIOS_FEATURE)
        spec = GherkinFeatureBridge.parse(p)
        assert spec.title == "A minimal feature with no scenarios"
        assert spec.scenarios == []

    def test_works_with_real_repo_feature_file(self):
        repo_feature = Path("features/project_aware_tdd.feature")
        if not repo_feature.exists():
            pytest.skip("feature file not present")
        spec = GherkinFeatureBridge.parse(repo_feature)
        assert spec.title
        assert len(spec.scenarios) > 0

    def test_strips_description_lines_before_first_scenario(self, tmp_path):
        p = _write_feature(tmp_path, SIMPLE_FEATURE)
        spec = GherkinFeatureBridge.parse(p)
        # "As a user", "I want..." lines must not appear as scenario names
        names = [s.name for s in spec.scenarios]
        assert all("As a" not in n and "I want" not in n for n in names)


# ---------------------------------------------------------------------------
# PolyglotTDDRunner.run_from_feature
# ---------------------------------------------------------------------------

def _stub_pod(tokens=100):
    from src.agents.language_pod import PhaseResult
    pod = MagicMock()
    pod.run_red.return_value = PhaseResult(passed=False, output="FAIL")
    pod.run_green.return_value = PhaseResult(passed=True, output="ok")
    pod.run_refactor.return_value = PhaseResult(passed=True, output="ok")
    pod.token_usage.return_value = [TokenUsage(cycle_number=1, input_tokens=tokens, output_tokens=0)]
    return pod


def _factory(pod):
    f = MagicMock()
    f.create.return_value = pod
    return f


class TestRunFromFeature:
    def test_returns_polyglot_run_result(self, tmp_path):
        from src.agents.polyglot_tdd_runner import PolyglotRunResult, PolyglotTDDRunner
        p = _write_feature(tmp_path, SIMPLE_FEATURE)
        pod = _stub_pod()
        runner = PolyglotTDDRunner(_factory(pod))
        result = runner.run_from_feature(
            feature_path=p,
            languages=["python"],
            test_file=tmp_path / "test_auth.py",
            implementation_file=tmp_path / "auth.py",
        )
        assert isinstance(result, PolyglotRunResult)

    def test_feature_title_used_as_requirement(self, tmp_path):
        from src.agents.polyglot_tdd_runner import PolyglotTDDRunner
        p = _write_feature(tmp_path, SIMPLE_FEATURE)
        pod = _stub_pod()
        runner = PolyglotTDDRunner(_factory(pod))
        runner.run_from_feature(
            feature_path=p,
            languages=["python"],
            test_file=tmp_path / "test_auth.py",
            implementation_file=tmp_path / "auth.py",
        )
        spec_arg = pod.run_red.call_args[0][0]
        assert "User authentication with JWT" in spec_arg.feature_requirement

    def test_efficiency_report_populated(self, tmp_path):
        from src.agents.polyglot_tdd_runner import PolyglotTDDRunner
        p = _write_feature(tmp_path, SIMPLE_FEATURE)
        pod = _stub_pod()
        runner = PolyglotTDDRunner(_factory(pod))
        result = runner.run_from_feature(
            feature_path=p,
            languages=["python"],
            test_file=tmp_path / "test_auth.py",
            implementation_file=tmp_path / "auth.py",
        )
        assert isinstance(result.efficiency_report, EfficiencyReport)
        assert len(result.efficiency_report.scores) == 1

    def test_missing_feature_line_raises(self, tmp_path):
        from src.agents.polyglot_tdd_runner import PolyglotTDDRunner
        p = _write_feature(tmp_path, NO_FEATURE_LINE)
        runner = PolyglotTDDRunner(_factory(_stub_pod()))
        with pytest.raises(ValueError):
            runner.run_from_feature(
                feature_path=p,
                languages=["python"],
                test_file=tmp_path / "t.py",
                implementation_file=tmp_path / "i.py",
            )
