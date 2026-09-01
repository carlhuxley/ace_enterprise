"""Tests for src/utils/topo.py — dependency ordering with a lexical tie-break."""
import pytest

from src.utils.topo import DependencyError, topo_order


def test_no_dependencies_is_lexical_by_input_order():
    assert topo_order(["c", "a", "b"], {}) == ["a", "b", "c"]


def test_dependencies_come_first():
    order = topo_order(
        sorted(["api", "auth", "db"]),
        {"auth": ["db"], "api": ["auth", "db"]},
    )
    assert order == ["db", "auth", "api"]


def test_ties_break_lexically_within_the_constraint():
    # both "x" and "y" depend on "a"; among the ready pair, lexical order.
    order = topo_order(sorted(["a", "y", "x"]), {"x": ["a"], "y": ["a"]})
    assert order == ["a", "x", "y"]


def test_unknown_dependency_raises():
    with pytest.raises(DependencyError, match="unknown node 'ghost'"):
        topo_order(["a"], {"a": ["ghost"]})


def test_dependency_declared_for_unknown_node_raises():
    with pytest.raises(DependencyError, match="unknown node 'ghost'"):
        topo_order(["a"], {"ghost": []})


def test_cycle_raises():
    with pytest.raises(DependencyError, match="cycle"):
        topo_order(["a", "b"], {"a": ["b"], "b": ["a"]})


def test_self_dependency_is_a_cycle():
    with pytest.raises(DependencyError, match="cycle"):
        topo_order(["a"], {"a": ["a"]})


def test_empty():
    assert topo_order([], {}) == []
