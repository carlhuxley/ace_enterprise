"""Integration tests for `topological_sort`, generated from its ModuleContract."""
from topological_sort import *  # noqa: F401,F403


def test_linear_chain():
    clear_dag()
    add_node('a')
    add_node('b')
    add_node('c')
    add_edge('a', 'b')
    add_edge('b', 'c')
    result = topological_sort()
    assert result == ['a', 'b', 'c']


def test_diamond_graph_lexical_order():
    clear_dag()
    add_node('a')
    add_node('b')
    add_node('c')
    add_node('d')
    add_edge('a', 'b')
    add_edge('a', 'c')
    add_edge('b', 'd')
    add_edge('c', 'd')
    result = topological_sort()
    assert result == ['a', 'b', 'c', 'd']


def test_multiple_roots_lexical_tie_breaking():
    clear_dag()
    add_node('z')
    add_node('a')
    add_node('m')
    add_node('x')
    add_edge('z', 'x')
    add_edge('a', 'x')
    result = topological_sort()
    assert result == ['a', 'm', 'z', 'x']


def test_cycle_returns_empty_list():
    clear_dag()
    add_node('a')
    add_node('b')
    add_node('c')
    add_edge('a', 'b')
    add_edge('b', 'c')
    add_edge('c', 'a')
    result = topological_sort()
    assert result == []


def test_single_node():
    clear_dag()
    add_node('only')
    result = topological_sort()
    assert result == ['only']


def test_empty_graph():
    clear_dag()
    result = topological_sort()
    assert result == []


def test_compute_in_degrees():
    clear_dag()
    add_node('a')
    add_node('b')
    add_node('c')
    add_edge('a', 'b')
    add_edge('a', 'c')
    add_edge('b', 'c')
    degrees = compute_in_degrees()
    assert degrees == {'a': 0, 'b': 1, 'c': 2}


def test_complex_dag_with_lexical_order():
    clear_dag()
    add_node('task1')
    add_node('task2')
    add_node('task3')
    add_node('task4')
    add_edge('task1', 'task3')
    add_edge('task2', 'task3')
    add_edge('task3', 'task4')
    result = topological_sort()
    assert result == ['task1', 'task2', 'task3', 'task4']
