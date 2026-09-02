"""Integration tests for `manifest_io`, generated from its ModuleContract."""
from manifest_io import *  # noqa: F401,F403
from manifest_io import _manifest_path  # noqa: F401


def test_save_and_load_empty_graph():
    clear_dag()
    save_dag()
    loaded = load_dag()
    assert loaded == {}


def test_save_and_load_nodes_only():
    clear_dag()
    add_node('a')
    add_node('b')
    save_dag()
    loaded = load_dag()
    nodes = get_nodes()
    assert set(nodes) == {'a', 'b'} and loaded == {'a': [], 'b': []}


def test_save_and_load_with_edges():
    clear_dag()
    add_node('x')
    add_node('y')
    add_node('z')
    add_edge('x', 'y')
    add_edge('x', 'z')
    save_dag()
    loaded = load_dag()
    edges_x = get_edges('x')
    assert set(edges_x) == {'y', 'z'} and loaded['x'] == ['y', 'z']


def test_load_creates_graph_structure():
    clear_dag()
    add_node('start')
    add_node('end')
    add_edge('start', 'end')
    save_dag()
    loaded = load_dag()
    nodes = get_nodes()
    edges = get_edges('start')
    assert 'start' in nodes and 'end' in nodes and 'end' in edges


def test_clear_removes_manifest():
    set_manifest_path('workspace/.ace/test_manifest.json')
    add_node('temp')
    save_dag()
    path = Path(get_manifest_path())
    exists_before = path.exists()
    clear_dag()
    exists_after = path.exists()
    assert exists_before == True and exists_after == False


def test_custom_manifest_path():
    clear_dag()
    set_manifest_path('workspace/.ace/custom.json')
    add_node('custom')
    save_dag()
    path = Path(get_manifest_path())
    exists = path.exists()
    assert exists == True and 'custom.json' in str(path)
