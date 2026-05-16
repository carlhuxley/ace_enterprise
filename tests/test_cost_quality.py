import pytest
from src.analytics.cost_quality_analyzer import CostQualityAnalyzer


# ---------------------------------------------------------------------------
# calculate_cost_efficiency_metrics
# ---------------------------------------------------------------------------

def test_efficiency_grade_A_when_quality_per_dollar_above_5000():
    analyzer = CostQualityAnalyzer({"accuracy": 0.95, "cost_per_prediction": 0.0001})
    result = analyzer.calculate_cost_efficiency_metrics()
    assert result["efficiency_grade"] == "A"


def test_efficiency_grade_B_when_quality_per_dollar_between_1000_and_5000():
    # 0.80 / 0.0004 = 2000, which is between 1000 and 5000 → grade B
    analyzer = CostQualityAnalyzer({"accuracy": 0.80, "cost_per_prediction": 0.0004})
    result = analyzer.calculate_cost_efficiency_metrics()
    assert result["efficiency_grade"] == "B"


def test_efficiency_grade_C_when_quality_per_dollar_below_1000():
    analyzer = CostQualityAnalyzer({"accuracy": 0.50, "cost_per_prediction": 0.01})
    result = analyzer.calculate_cost_efficiency_metrics()
    assert result["efficiency_grade"] == "C"


def test_cost_per_quality_point_rounds_to_6_decimal_places():
    analyzer = CostQualityAnalyzer({"accuracy": 0.3, "cost_per_prediction": 0.0001})
    result = analyzer.calculate_cost_efficiency_metrics()
    assert result["cost_per_quality_point"] == round(0.0001 / 0.3, 6)


def test_avg_quality_score_rounds_to_2_decimal_places():
    analyzer = CostQualityAnalyzer({"accuracy": 0.856789, "cost_per_prediction": 0.001})
    result = analyzer.calculate_cost_efficiency_metrics()
    assert result["avg_quality_score"] == round(0.856789, 2)


def test_metadata_contains_calculated_at_and_input_hash():
    analyzer = CostQualityAnalyzer({"accuracy": 0.9, "cost_per_prediction": 0.001})
    result = analyzer.calculate_cost_efficiency_metrics()
    assert "calculated_at" in result["metadata"]
    assert "input_hash" in result["metadata"]


def test_total_metrics_path_used_when_provided():
    analyzer = CostQualityAnalyzer({
        "total_cost_usd": 10.0,
        "total_quality_points": 50000.0,
        "task_count": 100,
    })
    result = analyzer.calculate_cost_efficiency_metrics()
    assert result["cost_per_quality_point"] == round(10.0 / 50000.0, 6)
    assert result["avg_quality_score"] == round(50000.0 / 100, 2)


# ---------------------------------------------------------------------------
# rank_models_by_quality_per_dollar
# ---------------------------------------------------------------------------

def test_rank_orders_highest_quality_per_dollar_first():
    models = [
        {"model_name": "cheap-bad",  "accuracy": 0.5, "cost_per_prediction": 0.01},
        {"model_name": "cheap-good", "accuracy": 0.9, "cost_per_prediction": 0.001},
        {"model_name": "pricey",     "accuracy": 0.95, "cost_per_prediction": 0.1},
    ]
    ranked = CostQualityAnalyzer.rank_models_by_quality_per_dollar(models)
    assert ranked[0]["model_name"] == "cheap-good"
    assert ranked[-1]["model_name"] == "pricey"


def test_rank_with_single_model_returns_that_model():
    models = [{"model_name": "only", "accuracy": 0.8, "cost_per_prediction": 0.01}]
    assert CostQualityAnalyzer.rank_models_by_quality_per_dollar(models) == models


# ---------------------------------------------------------------------------
# compute_pareto_frontier
# ---------------------------------------------------------------------------

def test_pareto_excludes_dominated_model():
    # "slow-expensive" is dominated by "fast-cheap" (lower cost, higher accuracy)
    models = [
        {"model_name": "fast-cheap",     "accuracy": 0.9, "cost_per_prediction": 0.001},
        {"model_name": "slow-expensive", "accuracy": 0.7, "cost_per_prediction": 0.01},
    ]
    frontier = CostQualityAnalyzer.compute_pareto_frontier(models)
    names = [m["model_name"] for m in frontier]
    assert "fast-cheap" in names
    assert "slow-expensive" not in names


def test_pareto_keeps_both_when_neither_dominates():
    # high accuracy at high cost vs low accuracy at low cost — neither dominates
    models = [
        {"model_name": "accurate",  "accuracy": 0.95, "cost_per_prediction": 0.1},
        {"model_name": "economical", "accuracy": 0.70, "cost_per_prediction": 0.001},
    ]
    frontier = CostQualityAnalyzer.compute_pareto_frontier(models)
    assert len(frontier) == 2


def test_pareto_single_model_is_always_on_frontier():
    models = [{"model_name": "only", "accuracy": 0.8, "cost_per_prediction": 0.01}]
    assert CostQualityAnalyzer.compute_pareto_frontier(models) == models


# ---------------------------------------------------------------------------
# calculate_quality_delta_percentage
# ---------------------------------------------------------------------------

def test_quality_delta_percentage_formula():
    higher = {"accuracy": 0.9}
    lower  = {"accuracy": 0.8}
    delta = CostQualityAnalyzer.calculate_quality_delta_percentage(higher, lower)
    assert abs(delta - 12.5) < 1e-9  # ((0.9 - 0.8) / 0.8) * 100


def test_quality_delta_is_zero_for_identical_models():
    model = {"accuracy": 0.85}
    assert CostQualityAnalyzer.calculate_quality_delta_percentage(model, model) == 0.0


# ---------------------------------------------------------------------------
# query_best_model_for_complexity
# ---------------------------------------------------------------------------

def _make_model(name, complexity, success_rate, cost, value_score):
    return {
        "model_name": name,
        "complexity": complexity,
        "success_rate": success_rate,
        "cost_per_prediction": cost,
        "value_score": value_score,
    }


def test_high_complexity_requires_90_percent_success_rate():
    models = [
        _make_model("marginal", "high", 0.85, 0.01, 100),  # below threshold
        _make_model("solid",    "high", 0.92, 0.02, 80),   # above threshold
    ]
    best = CostQualityAnalyzer.query_best_model_for_complexity(models, "high")
    assert best["model_name"] == "solid"


def test_selects_highest_value_score_among_qualifying_models():
    models = [
        _make_model("ok",   "medium", 0.82, 0.01, 50),
        _make_model("best", "medium", 0.90, 0.02, 95),
        _make_model("good", "medium", 0.85, 0.015, 70),
    ]
    best = CostQualityAnalyzer.query_best_model_for_complexity(models, "medium")
    assert best["model_name"] == "best"


def test_falls_back_to_all_models_when_none_meet_threshold():
    models = [
        _make_model("low-acc-high-value", "high", 0.50, 0.001, 999),
        _make_model("low-acc-low-value",  "high", 0.60, 0.002, 10),
    ]
    # Neither meets the 0.90 threshold — fall back, pick highest value_score
    best = CostQualityAnalyzer.query_best_model_for_complexity(models, "high")
    assert best["model_name"] == "low-acc-high-value"


def test_raises_for_unknown_complexity_level():
    models = [_make_model("m", "high", 0.95, 0.01, 80)]
    with pytest.raises(ValueError, match="No models found"):
        CostQualityAnalyzer.query_best_model_for_complexity(models, "unknown")
