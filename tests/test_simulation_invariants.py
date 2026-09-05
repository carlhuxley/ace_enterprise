"""Tests for MetricBound extraction from Gherkin scenario text."""
from src.agents.simulation_invariants import MetricBound, extract_invariants


class TestEmptyInput:
    def test_none_text_returns_no_bounds(self):
        assert extract_invariants(None) == []

    def test_empty_text_returns_no_bounds(self):
        assert extract_invariants("") == []

    def test_text_with_no_matching_clauses_returns_no_bounds(self):
        text = "Feature: Insert the peg\n  Scenario: it seats\n    Given a peg above a hole"
        assert extract_invariants(text) == []


class TestUpperBound:
    def test_extracts_instantaneous_upper_bound(self):
        text = "Then the peak force must never exceed 12.0"
        result = extract_invariants(text)
        assert result == [MetricBound("peak_force", "<=", 12.0, "instantaneous")]

    def test_metric_name_is_normalized_to_snake_case(self):
        text = "Then the actuator temperature must never exceed 80"
        result = extract_invariants(text)
        assert result[0].metric == "actuator_temperature"

    def test_extracts_multiple_upper_bounds(self):
        text = """
        Then the peak force must never exceed 12.0
        And the torque must never exceed 4.5
        """
        result = extract_invariants(text)
        metrics = {b.metric: b.threshold for b in result}
        assert metrics == {"peak_force": 12.0, "torque": 4.5}


class TestLowerBound:
    def test_extracts_instantaneous_lower_bound(self):
        text = "And the grip force must maintain >= 3.0"
        result = extract_invariants(text)
        assert result == [MetricBound("grip_force", ">=", 3.0, "instantaneous")]


class TestConvergenceTarget:
    def test_extracts_final_bound_with_step_budget(self):
        text = "And final radial error must reach <= 0.0015 within 500 steps"
        result = extract_invariants(text)
        assert result == [MetricBound("radial_error", "<=", 0.0015, "final", within_steps=500)]

    def test_step_suffix_is_optional(self):
        text = "And final depth must reach <= 0.024 within 500"
        result = extract_invariants(text)
        assert result[0].within_steps == 500


class TestFullScenario:
    def test_extracts_a_mix_of_bound_kinds(self):
        text = """
        Feature: Peg-in-hole insertion
          Scenario: The peg seats without a jam
            Then the peak force must never exceed 12.0
            And the grip force must maintain >= 3.0
            And final radial error must reach <= 0.0015 within 500 steps
            And final depth must reach <= 0.024 within 500 steps
        """
        result = extract_invariants(text)
        assert result == [
            MetricBound("peak_force", "<=", 12.0, "instantaneous"),
            MetricBound("grip_force", ">=", 3.0, "instantaneous"),
            MetricBound("radial_error", "<=", 0.0015, "final", within_steps=500),
            MetricBound("depth", "<=", 0.024, "final", within_steps=500),
        ]
