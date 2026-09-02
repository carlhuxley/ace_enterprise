"""Integration tests for `cycle_detector`, generated from its ModuleContract."""
from cycle_detector import *  # noqa: F401,F403
from cycle_detector import _graph, _visited, _rec_stack  # noqa: F401


def test_simple_cycle():
    _graph.clear(); _visited.clear(); _rec_stack.clear()
    add_edge('A', 'B')
    add_edge('B', 'C')
    add_edge('C', 'A')
    result = has_cycle()
    assert result == True


def test_no_cycle_linear():
    _graph.clear(); _visited.clear(); _rec_stack.clear()
    add_edge('A', 'B')
    add_edge('B', 'C')
    add_edge('C', 'D')
    result = has_cycle()
    assert result == False


def test_self_loop():
    _graph.clear(); _visited.clear(); _rec_stack.clear()
    add_edge('A', 'A')
    result = has_cycle()
    assert result == True


def test_empty_graph():
    _graph.clear(); _visited.clear(); _rec_stack.clear()
    result = has_cycle()
    assert result == False


def test_disconnected_with_cycle():
    _graph.clear(); _visited.clear(); _rec_stack.clear()
    add_edge('A', 'B')
    add_edge('B', 'C')
    add_edge('D', 'E')
    add_edge('E', 'F')
    add_edge('F', 'D')
    result = has_cycle()
    assert result == True


def test_find_cycle_returns_path():
    _graph.clear(); _visited.clear(); _rec_stack.clear()
    add_edge('A', 'B')
    add_edge('B', 'C')
    add_edge('C', 'D')
    add_edge('D', 'B')
    cycle = find_cycle()
    assert len(cycle) > 0 and 'B' in cycle and 'C' in cycle and 'D' in cycle


def test_find_cycle_no_cycle():
    _graph.clear(); _visited.clear(); _rec_stack.clear()
    add_edge('A', 'B')
    add_edge('B', 'C')
    cycle = find_cycle()
    assert cycle == []


def test_isolated_nodes():
    _graph.clear(); _visited.clear(); _rec_stack.clear()
    add_node('A')
    add_node('B')
    add_node('C')
    result = has_cycle()
    assert result == False


def test_get_nodes_and_edges():
    _graph.clear(); _visited.clear(); _rec_stack.clear()
    add_edge('A', 'B')
    add_edge('A', 'C')
    add_edge('B', 'D')
    nodes = get_nodes()
    edges_a = get_edges('A')
    edges_b = get_edges('B')
    assert set(nodes) == {'A', 'B', 'C', 'D'} and set(edges_a) == {'B', 'C'} and edges_b == ['D']


def test_complex_cycle():
    _graph.clear(); _visited.clear(); _rec_stack.clear()
    add_edge('A', 'B')
    add_edge('B', 'C')
    add_edge('C', 'D')
    add_edge('D', 'E')
    add_edge('E', 'C')
    add_edge('A', 'F')
    result = has_cycle()
    cycle = find_cycle()
    assert result == True and len(cycle) > 0
