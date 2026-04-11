# Test file for cost_quality
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.cost_quality import *

def test_cost_quality_analyzer_calculates_cost_per_quality_point():
    analyzer = CostQualityAnalyzer()
    cost = 100
    quality = 5
    result = analyzer.calculate_cost_per_quality_point(cost, quality)
    assert result == 20.0