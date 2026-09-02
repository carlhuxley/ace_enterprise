"""Integration tests for `persistent_dag`, generated from its ModuleContract."""
from persistent_dag import *  # noqa: F401,F403
from persistent_dag import _registry  # noqa: F401


def test_register_module_success():
    _registry.clear(); clear_dag()
    result = register_module('auth', [])
    nodes = get_nodes()
    assert result['success'] == True and result['error'] is None and 'auth' in nodes


def test_register_module_with_dependencies():
    _registry.clear(); clear_dag()
    register_module('core', [])
    result = register_module('auth', ['core'])
    edges = get_edges('auth')
    assert result['success'] == True and 'core' in edges


def test_register_module_detects_cycle():
    _registry.clear(); clear_dag()
    register_module('a', [])
    register_module('b', ['a'])
    register_module('c', ['b'])
    result = register_module('a', ['c'])
    assert result['success'] == False and result['error'] is not None and 'cycle' in result['error'].lower()


def test_build_order_linear_dependencies():
    _registry.clear(); clear_dag()
    register_module('core', [])
    register_module('auth', ['core'])
    register_module('api', ['auth'])
    order = build_order()
    assert order == ['core', 'auth', 'api']


def test_build_order_diamond_dependencies():
    _registry.clear(); clear_dag()
    register_module('core', [])
    register_module('auth', ['core'])
    register_module('db', ['core'])
    register_module('api', ['auth', 'db'])
    order = build_order()
    assert order.index('core') < order.index('auth') and order.index('core') < order.index('db') and order.index('auth') < order.index('api') and order.index('db') < order.index('api')


def test_build_order_with_cycle_returns_empty():
    _registry.clear(); clear_dag()
    register_module('a', [])
    register_module('b', ['a'])
    add_edge('a', 'b')
    order = build_order()
    assert order == []


def test_blast_radius_single_dependent():
    _registry.clear(); clear_dag()
    register_module('core', [])
    register_module('auth', ['core'])
    radius = blast_radius('core')
    assert radius == ['auth']


def test_blast_radius_transitive_dependents():
    _registry.clear(); clear_dag()
    register_module('core', [])
    register_module('auth', ['core'])
    register_module('api', ['auth'])
    register_module('ui', ['api'])
    radius = blast_radius('core')
    assert set(radius) == {'auth', 'api', 'ui'}


def test_blast_radius_no_dependents():
    _registry.clear(); clear_dag()
    register_module('core', [])
    register_module('auth', ['core'])
    radius = blast_radius('auth')
    assert radius == []


def test_blast_radius_nonexistent_module():
    _registry.clear(); clear_dag()
    register_module('core', [])
    radius = blast_radius('nonexistent')
    assert radius == []


def test_load_manifest_restores_state():
    _registry.clear(); clear_dag()
    register_module('core', [])
    register_module('auth', ['core'])
    _registry.clear(); clear_dag()
    manifest = load_manifest()
    order = build_order()
    assert 'core' in manifest and 'auth' in manifest and order == ['core', 'auth']


def test_register_module_persists_atomically():
    _registry.clear(); clear_dag()
    register_module('core', [])
    register_module('auth', ['core'])
    _registry.clear(); clear_dag()
    loaded = load_manifest()
    assert loaded == {'core': [], 'auth': ['core']}


def test_blast_radius_diamond_pattern():
    _registry.clear(); clear_dag()
    register_module('core', [])
    register_module('auth', ['core'])
    register_module('db', ['core'])
    register_module('api', ['auth', 'db'])
    radius = blast_radius('core')
    assert set(radius) == {'auth', 'db', 'api'}
