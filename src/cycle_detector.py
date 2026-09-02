# cycle_detector
# Detects cycles in directed graphs using DFS with recursion stack tracking

# Shared state
_graph: dict[str, list[str]] = {}
_visited: set[str] = set()
_rec_stack: set[str] = set()


def add_edge(from_node: str, to_node: str) -> None:
    """Add a directed edge from from_node to to_node in the graph"""
    if from_node not in _graph:
        _graph[from_node] = []
    _graph[from_node].append(to_node)
    
    # Ensure to_node exists in graph even if it has no outgoing edges
    if to_node not in _graph:
        _graph[to_node] = []

def add_node(node: str) -> None:
    """Add an isolated node to the graph with no edges"""
    if node not in _graph:
        _graph[node] = []

def has_cycle() -> bool:
    """Check if the graph contains any cycle using DFS with recursion stack"""
    _visited.clear()
    _rec_stack.clear()
    
    def dfs(node: str) -> bool:
        _visited.add(node)
        _rec_stack.add(node)
        
        for neighbor in _graph.get(node, []):
            if neighbor not in _visited:
                if dfs(neighbor):
                    return True
            elif neighbor in _rec_stack:
                return True
        
        _rec_stack.remove(node)
        return False
    
    for node in _graph:
        if node not in _visited:
            if dfs(node):
                return True
    
    return False

def find_cycle() -> list[str]:
    """Return a list of nodes forming a cycle, or empty list if no cycle exists"""
    _visited.clear()
    _rec_stack.clear()
    
    def dfs(node: str, path: list[str]) -> list[str]:
        _visited.add(node)
        _rec_stack.add(node)
        path.append(node)
        
        for neighbor in _graph.get(node, []):
            if neighbor not in _visited:
                result = dfs(neighbor, path)
                if result:
                    return result
            elif neighbor in _rec_stack:
                # Found a cycle - return the cycle portion of the path
                cycle_start = path.index(neighbor)
                return path[cycle_start:]
        
        _rec_stack.remove(node)
        path.pop()
        return []
    
    for node in _graph:
        if node not in _visited:
            result = dfs(node, [])
            if result:
                return result
    
    return []

def get_nodes() -> list[str]:
    """Return all nodes in the graph"""
    return list(_graph.keys())

def get_edges(node: str) -> list[str]:
    """Return all outgoing edges from a given node"""
    return _graph.get(node, [])
