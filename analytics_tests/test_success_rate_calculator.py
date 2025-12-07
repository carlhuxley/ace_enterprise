# Test file for success_rate_calculator
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.success_rate_calculator import *

def test_success_rate_calculator_can_be_created():
    calc = SuccessRateCalculator()
    assert calc is not None