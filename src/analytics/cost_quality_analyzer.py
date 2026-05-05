# src/cost_quality_analyzer.py
import hashlib
import math
from datetime import datetime, timezone


class CostQualityAnalyzer:
    """Analyzes cost-quality tradeoffs for ML model performance data."""
    
    def __init__(self, performance_data: dict):
        """Initialize with model performance data.
        
        Args:
            performance_data: Dictionary containing model metrics including:
                - model_name: Name of the model
                - accuracy: Model accuracy score (0-1)
                - cost_per_prediction: Cost for each prediction
                - latency_ms: Prediction latency in milliseconds
                - total_cost_usd: Total cost in USD
                - total_quality_points: Total quality points accumulated
                - task_count: Number of tasks processed
        """
        self.performance_data = performance_data
        self.model_name = performance_data.get("model_name")
        self.accuracy = performance_data.get("accuracy")
        self.cost_per_prediction = performance_data.get("cost_per_prediction")
        self.latency_ms = performance_data.get("latency_ms")
        # Additional fields for total metrics
        self.total_cost_usd = performance_data.get("total_cost_usd")
        self.total_quality_points = performance_data.get("total_quality_points")
        self.task_count = performance_data.get("task_count")
    
    def calculate_cost_efficiency_metrics(self) -> dict:
        """Calculate cost efficiency metrics from the stored performance data.
        
        Returns:
            Dictionary containing:
                - cost_per_quality_point: Cost spent per unit of quality (accuracy), rounded to 6 decimal places
                - quality_per_dollar: Quality (accuracy) obtained per dollar spent
                - avg_quality_score: Average quality score, rounded to 2 decimal places
                - efficiency_grade: Grade based on quality_per_dollar thresholds (A>=5000, B>=1000, C<1000)
                - metadata: Dictionary with calculated_at (ISO timestamp) and input_hash (SHA256)
        """
        # Check if we have total metrics or per-prediction metrics
        if self.total_cost_usd is not None and self.total_quality_points is not None:
            # Use total metrics calculation
            raw_cost_per_quality_point = self.total_cost_usd / self.total_quality_points
            quality_per_dollar = float(self.total_quality_points / self.total_cost_usd)
            raw_avg_quality_score = self.total_quality_points / self.task_count if self.task_count else self.total_quality_points
        else:
            # Use per-prediction metrics calculation (original behavior)
            raw_cost_per_quality_point = self.cost_per_prediction / self.accuracy
            quality_per_dollar = float(self.accuracy / self.cost_per_prediction)
            raw_avg_quality_score = self.accuracy
        
        # Apply required rounding
        cost_per_quality_point = round(raw_cost_per_quality_point, 6)
        avg_quality_score = round(raw_avg_quality_score, 2)
        
        # Determine efficiency grade based on quality_per_dollar thresholds
        if quality_per_dollar >= 5000:
            efficiency_grade = "A"
        elif quality_per_dollar >= 1000:
            efficiency_grade = "B"
        else:
            efficiency_grade = "C"
        
        # Generate metadata with ISO timestamp and deterministic input hash
        input_hash = hashlib.sha256(
            str(sorted(self.performance_data.items())).encode()
        ).hexdigest()
        
        metadata = {
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "input_hash": input_hash
        }
        
        return {
            "cost_per_quality_point": cost_per_quality_point,
            "quality_per_dollar": quality_per_dollar,
            "avg_quality_score": avg_quality_score,
            "efficiency_grade": efficiency_grade,
            "metadata": metadata
        }
    
    @staticmethod
    def rank_models_by_quality_per_dollar(models_data: list) -> list:
        """Rank multiple models by their quality per dollar metric.
        
        Args:
            models_data: List of dictionaries containing model performance data,
                        each with at least 'model_name', 'accuracy', and 
                        'cost_per_prediction' fields.
        
        Returns:
            List of model dictionaries sorted by quality_per_dollar in descending order
            (highest value first).
        """
        return sorted(
            models_data,
            key=lambda m: m["accuracy"] / m["cost_per_prediction"],
            reverse=True
        )
    
    @staticmethod
    def compute_pareto_frontier(models_data: list) -> list:
        """Compute the Pareto frontier of models based on cost and quality.
        
        A model is on the Pareto frontier if no other model has both:
        - Lower cost (cost_per_prediction)
        - Higher quality (accuracy)
        
        Args:
            models_data: List of dictionaries containing model performance data,
                        each with at least 'model_name', 'accuracy', and 
                        'cost_per_prediction' fields.
        
        Returns:
            List of model dictionaries that are on the Pareto frontier.
        """
        frontier = []
        
        for model in models_data:
            is_dominated = False
            for other_model in models_data:
                if other_model is model:
                    continue
                # Check if other_model dominates this model
                # Other model has lower cost AND higher quality
                if (other_model["cost_per_prediction"] < model["cost_per_prediction"] and
                    other_model["accuracy"] > model["accuracy"]):
                    is_dominated = True
                    break
            
            if not is_dominated:
                frontier.append(model)
        
        return frontier
    
    @staticmethod
    def calculate_quality_delta_percentage(higher_quality_model: dict, lower_quality_model: dict) -> float:
        """Calculate the percentage improvement in quality between two models.
        
        Args:
            higher_quality_model: Model dictionary with higher accuracy (contains 'accuracy' field)
            lower_quality_model: Model dictionary with lower accuracy (contains 'accuracy' field)
        
        Returns:
            Float representing the percentage improvement from lower_quality_model 
            to higher_quality_model.
            
        Formula: ((higher_accuracy - lower_accuracy) / lower_accuracy) * 100
        """
        higher_accuracy = higher_quality_model["accuracy"]
        lower_accuracy = lower_quality_model["accuracy"]
        
        delta_percentage = ((higher_accuracy - lower_accuracy) / lower_accuracy) * 100
        
        return delta_percentage
    
    @staticmethod
    def query_best_model_for_complexity(models_data: list, complexity_level: str) -> dict:
        """Find the optimal model for a given complexity level by balancing success_rate and value_score.

        Uses a threshold-based approach: for high-complexity tasks, filters models
        that meet a minimum accuracy threshold, then selects by value score.
        This ensures adequate accuracy while optimizing cost efficiency.

        Complexity thresholds (min_success_rate):
        - 'high':   0.90 (require high accuracy, then optimize value)
        - 'medium': 0.80 (moderate accuracy threshold)
        - 'low':    0.70 (lower threshold, more value-focused)

        Args:
            models_data: List of dictionaries containing model performance data,
                        each with 'model_name', 'complexity', 'success_rate',
                        'cost_per_prediction', and 'value_score' fields.
            complexity_level: String indicating the complexity level to filter by
                            (e.g., "high", "medium", "low").

        Returns:
            Dictionary representing the model with the best balance of success_rate
            and value_score for the specified complexity level.
        """
        # Filter models by complexity level
        filtered_models = [
            m for m in models_data
            if m.get("complexity") == complexity_level
        ]

        if not filtered_models:
            raise ValueError(f"No models found for complexity level: {complexity_level}")

        # Define minimum success rate thresholds by complexity
        # High complexity requires higher accuracy before considering cost
        complexity_thresholds = {
            "high": 0.90,
            "medium": 0.80,
            "low": 0.70
        }

        min_threshold = complexity_thresholds.get(complexity_level, 0.80)

        # Filter models meeting the accuracy threshold
        qualifying_models = [
            m for m in filtered_models
            if m.get("success_rate", 0) >= min_threshold
        ]

        # If no models meet threshold, fall back to all models
        if not qualifying_models:
            qualifying_models = filtered_models

        # Among qualifying models, select the one with best value_score
        # (best cost efficiency while meeting accuracy requirements)
        return max(qualifying_models, key=lambda m: m.get("value_score", 0))