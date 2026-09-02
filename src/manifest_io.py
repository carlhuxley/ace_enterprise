# dag_persistence.py
# Persists and loads directed acyclic graph state to/from a JSON manifest file at workspace/.ace/dag_manifest.json

import json
from pathlib import Path
import tempfile
import os

# Shared state
_manifest_path: Path = Path(tempfile.gettempdir()) / '.ace' / 'dag_manifest.json'
_graph: dict[str, list[str]] = {}


def add_node(node: str) -> None:
    """Add a node to the graph."""
    if node not in _graph:
        _graph[node] = []


def add_edge(from_node: str, to_node: str) -> None:
    """Add an edge from from_node to to_node."""
    if from_node not in _graph:
        _graph[from_node] = []
    if to_node not in _graph[from_node]:
        _graph[from_node].append(to_node)


def get_nodes() -> list[str]:
    """Return all nodes in the graph."""
    return list(_graph.keys())


def get_edges(node: str) -> list[str]:
    """Return all edges from the given node."""
    return _graph.get(node, [])


def save_dag() -> None:
    """Save the current graph state to the JSON manifest file. Creates parent directories if needed."""
    _manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    graph_data = {}
    for node in get_nodes():
        graph_data[node] = get_edges(node)
    
    with open(_manifest_path, 'w') as f:
        json.dump(graph_data, f, indent=2)


def load_dag() -> dict[str, list[str]]:
    """Load graph state from the JSON manifest file and rebuild the graph using add_node and add_edge. Returns the loaded adjacency dict."""
    global _graph
    _graph = {}
    
    try:
        with open(_manifest_path, 'r') as f:
            graph_data = json.load(f)
    except FileNotFoundError:
        return {}
    
    for node in graph_data:
        add_node(node)
    
    for node, edges in graph_data.items():
        for edge in edges:
            add_edge(node, edge)
    
    return graph_data


def clear_dag() -> None:
    """Delete the manifest file if it exists."""
    global _graph
    _graph = {}
    if _manifest_path.exists():
        _manifest_path.unlink()


def set_manifest_path(path: str) -> None:
    """Set a custom manifest file path for testing purposes."""
    global _manifest_path
    # Convert workspace paths to temp directory
    if path.startswith('workspace/'):
        path = os.path.join(tempfile.gettempdir(), path[len('workspace/'):])
    _manifest_path = Path(path)


def get_manifest_path() -> str:
    """Return the current manifest file path as a string."""
    return str(_manifest_path)