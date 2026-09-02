# module_registry.py
# Manages module dependencies as a DAG, validates cycles, computes build order, and calculates blast radius for impact analysis. Persists module registry to manifest file with atomic writes.

import json
from pathlib import Path
from collections import deque
import tempfile
import os

# Shared state
_registry: dict[str, list[str]] = {}


def clear_dag():
    """Clear the in-memory DAG state only.

    The persisted manifest on disk is left intact so load_manifest() can
    reconstruct the graph after an in-memory reset (that is exactly what the
    persistence tests exercise). Delete module_manifest.json directly if you
    want a clean slate on disk too.
    """
    global _registry
    _registry = {}


def get_nodes() -> list[str]:
    """Get all nodes in the DAG."""
    global _registry
    return list(_registry.keys())


def get_edges(module_name: str) -> list[str]:
    """Get all edges (dependencies) for a module."""
    global _registry
    return _registry.get(module_name, [])


def add_edge(from_module: str, to_module: str):
    """Add an edge from from_module to to_module (from_module depends on to_module)."""
    global _registry
    if from_module not in _registry:
        _registry[from_module] = []
    if to_module not in _registry[from_module]:
        _registry[from_module].append(to_module)


def _persist_manifest():
    """Persist the current registry to the manifest file atomically."""
    manifest_path = Path("module_manifest.json")
    
    try:
        # Use tempfile in the same directory for atomic rename
        fd, temp_path = tempfile.mkstemp(dir=manifest_path.parent, prefix='.module_manifest_', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(_registry, f, indent=2)
            os.replace(temp_path, manifest_path)
        except:
            os.unlink(temp_path)
            raise
    except Exception:
        raise


def register_module(module_name: str, dependencies: list[str]) -> dict[str, bool | str | None]:
    """Register a module with its dependencies. Validates that adding this module won't create a cycle. Returns dict with keys: 'success' (bool), 'error' (str or None), 'cycle' (list[str] or None). On success, adds module to graph and persists to manifest."""
    global _registry
    
    # Store original state in case we need to rollback
    original_registry = {k: v[:] for k, v in _registry.items()}
    
    # Add module to registry
    _registry[module_name] = dependencies.copy()
    
    # Check for cycles by doing a DFS from each node
    def has_cycle_dfs(node, visited, rec_stack, path):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)
        
        for neighbor in _registry.get(node, []):
            if neighbor not in _registry:
                # Dependency doesn't exist, skip it
                continue
            if neighbor not in visited:
                cycle = has_cycle_dfs(neighbor, visited, rec_stack, path[:])
                if cycle:
                    return cycle
            elif neighbor in rec_stack:
                # Found a cycle
                idx = path.index(neighbor)
                return path[idx:] + [neighbor]
        
        rec_stack.remove(node)
        path.pop()
        return None
    
    # Check for cycles
    visited = set()
    cycle_found = None
    for node in _registry:
        if node not in visited:
            cycle_found = has_cycle_dfs(node, visited, set(), [])
            if cycle_found:
                break
    
    if cycle_found:
        # Cycle detected, rollback
        _registry.clear()
        _registry.update(original_registry)
        return {
            'success': False,
            'error': 'Cycle detected',
            'cycle': cycle_found
        }
    
    # No cycle, persist and return success
    _persist_manifest()
    return {
        'success': True,
        'error': None,
        'cycle': None
    }


def load_manifest() -> dict[str, list[str]]:
    """Load the module registry from the persisted manifest file. Returns dict mapping module names to their dependency lists. Rebuilds the internal graph state and _registry."""
    global _registry
    
    manifest_path = Path("module_manifest.json")
    
    if not manifest_path.exists():
        _registry = {}
        return {}
    
    try:
        with open(manifest_path, 'r') as f:
            loaded_data = json.load(f)
        
        _registry = loaded_data
        return loaded_data
    except (json.JSONDecodeError, IOError):
        _registry = {}
        return {}


def build_order() -> list[str]:
    """Compute and return the topological build order of all registered modules. Returns empty list if the dependency graph has a cycle. Uses lexicographic tie-breaking for deterministic results."""
    global _registry
    
    if not _registry:
        return []
    
    # Check for cycles first
    def has_cycle_dfs(node, visited, rec_stack):
        visited.add(node)
        rec_stack.add(node)
        
        for neighbor in _registry.get(node, []):
            if neighbor not in _registry:
                continue
            if neighbor not in visited:
                if has_cycle_dfs(neighbor, visited, rec_stack):
                    return True
            elif neighbor in rec_stack:
                return True
        
        rec_stack.remove(node)
        return False
    
    visited = set()
    for node in _registry:
        if node not in visited:
            if has_cycle_dfs(node, visited, set()):
                return []
    
    # Compute in-degrees
    in_degree = {node: 0 for node in _registry}
    
    for node in _registry:
        for dep in _registry[node]:
            if dep in in_degree:
                in_degree[node] += 1
    
    # Kahn's algorithm with lexicographic ordering
    queue = sorted([node for node in in_degree if in_degree[node] == 0])
    result = []
    
    while queue:
        # Pop the lexicographically smallest node
        current = queue.pop(0)
        result.append(current)
        
        # Find all nodes that depend on current
        dependents = []
        for node in _registry:
            if current in _registry[node]:
                in_degree[node] -= 1
                if in_degree[node] == 0:
                    dependents.append(node)
        
        # Add to queue in sorted order
        queue.extend(dependents)
        queue.sort()
    
    # If we haven't processed all nodes, there's a cycle
    if len(result) != len(_registry):
        return []
    
    return result


def blast_radius(module_name: str) -> list[str]:
    """Calculate the blast radius for a module: all modules that directly or transitively depend on it. Returns sorted list of affected module names (excluding the module itself). Returns empty list if module not found."""
    global _registry
    
    # Check if module exists
    if module_name not in _registry:
        return []
    
    # Build reverse dependency graph (who depends on whom)
    reverse_deps = {node: [] for node in _registry}
    for node in _registry:
        for dep in _registry[node]:
            if dep in reverse_deps:
                reverse_deps[dep].append(node)
    
    # BFS/DFS to find all modules that depend on module_name
    affected = set()
    stack = [module_name]
    visited = set()
    
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        
        for dependent in reverse_deps.get(current, []):
            if dependent not in affected:
                affected.add(dependent)
                stack.append(dependent)
    
    # Return sorted list, excluding the module itself
    return sorted(affected)