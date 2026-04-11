class CostQualityAnalyzer:
    def __init__(self):
        self.model_performances = {}

    def calculate_cost_per_quality_point(self, cost, quality):
        return cost / quality

    def calculate_quality_per_dollar(self, cost, quality):
        return quality / cost

    def store_model_performance(self, model_name, cost, quality, task_count=None, model_id=None, roi=None):
        self.model_performances[model_name] = {"cost": cost, "quality": quality}
        if task_count is not None:
            self.model_performances[model_name]["task_count"] = task_count
        if model_id is not None:
            self.model_performances[model_name]["model_id"] = model_id
        if roi is not None:
            self.model_performances[model_name]["roi"] = roi
        
        # Ensure all expected keys exist even if not explicitly provided
        if "task_count" not in self.model_performances[model_name]:
            self.model_performances[model_name]["task_count"] = None
        if "model_id" not in self.model_performances[model_name]:
            self.model_performances[model_name]["model_id"] = None
        if "roi" not in self.model_performances[model_name]:
            self.model_performances[model_name]["roi"] = None

    def calculate_cost_efficiency_metrics(self, model_name, cost, quality, model_id=None):
        cost_efficiency = self.calculate_cost_per_quality_point(cost, quality)
        quality_per_dollar = self.calculate_quality_per_dollar(cost, quality)
        self.model_performances[model_name] = {"cost": cost, "quality": quality, "cost_efficiency": cost_efficiency, "quality_per_dollar": quality_per_dollar}
        if model_id is not None:
            self.model_performances[model_name]["model_id"] = model_id

        # Ensure all expected keys exist even if not explicitly provided
        if "cost_efficiency" not in self.model_performances[model_name]:
            self.model_performances[model_name]["cost_efficiency"] = cost_efficiency
        if "quality_per_dollar" not in self.model_performances[model_name]:
            self.model_performances[model_name]["quality_per_dollar"] = quality_per_dollar
        if "model_id" not in self.model_performances[model_name]:
            self.model_performances[model_name]["model_id"] = model_id if model_id else None

    def calculate_avg_quality_score(self):
        total_quality = sum(model["quality"] for model in self.model_performances.values())
        return total_quality / len(self.model_performances)