"""
Unit tests for calculator module.

This is a realistic test file that exists BEFORE implementation.
ACE will read this test and generate the implementation to make it pass.
"""
import pytest


def test_add_two_numbers():
    """Test basic addition"""
    from calculator import add
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0


def test_add_negative_numbers():
    """Test addition with negative numbers"""
    from calculator import add
    assert add(-5, -3) == -8
    assert add(-10, 5) == -5


def test_multiply_two_numbers():
    """Test basic multiplication"""
    from calculator import multiply
    assert multiply(3, 4) == 12
    assert multiply(0, 5) == 0
    assert multiply(-2, 3) == -6


def test_divide_two_numbers():
    """Test basic division"""
    from calculator import divide
    assert divide(10, 2) == 5.0
    assert divide(7, 2) == 3.5
    assert divide(-10, 2) == -5.0


def test_divide_by_zero_raises_error():
    """Test that dividing by zero raises appropriate error"""
    from calculator import divide
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide(5, 0)
