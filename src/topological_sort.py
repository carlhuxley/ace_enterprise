# topological_sort.py
# Computes topological ordering of a directed acyclic graph with lexical tie-breaking using Kahn's algorithm

import heapq

# Global graph state
_nodes = set()
_edges = []


def clear_dag():
    """Clear the graph state"""
    global _nodes, _edges
    _nodes = set()
    _edges = []


def add_node(node: str):
    """Add a node to the graph"""
    global _nodes
    _nodes.add(node)


def add_edge(source: str, target: str):
    """Add an edge to the graph"""
    global _edges
    _edges.append((source, target))


def get_nodes():
    """Get all nodes in the graph"""
    return _nodes


def get_edges():
    """Get all edges in the graph"""
    return _edges


def has_cycle() -> bool:
    """Check if the graph has a cycle using DFS"""
    adjacency = {node: [] for node in _nodes}
    for source, target in _edges:
        adjacency[source].append(target)
    
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in _nodes}
    
    def dfs(node):
        if color[node] == GRAY:
            return True  # Back edge found, cycle exists
        if color[node] == BLACK:
            return False  # Already processed
        
        color[node] = GRAY
        for neighbor in adjacency[node]:
            if dfs(neighbor):
                return True
        color[node] = BLACK
        return False
    
    for node in _nodes:
        if color[node] == WHITE:
            if dfs(node):
                return True
    
    return False


def compute_in_degrees() -> dict[str, int]:
    """Compute and return the in-degree (number of incoming edges) for each node in the graph"""
    # Initialize in-degrees to 0 for all nodes
    in_degrees = {node: 0 for node in _nodes}
    
    # Count incoming edges for each node
    for source, target in _edges:
        in_degrees[target] += 1
    
    return in_degrees


def topological_sort() -> list[str]:
    """Return nodes in topological order using Kahn's algorithm with lexical tie-breaking. Returns empty list if graph has a cycle. When multiple nodes have zero in-degree, processes them in lexicographic order."""
    # Check for cycles first
    if has_cycle():
        return []
    
    # Get in-degrees for all nodes
    in_degrees = compute_in_degrees()
    
    # Build adjacency list
    adjacency = {node: [] for node in _nodes}
    for source, target in _edges:
        adjacency[source].append(target)
    
    # Initialize min-heap with all zero in-degree nodes (lexical order)
    heap = [node for node, degree in in_degrees.items() if degree == 0]
    heapq.heapify(heap)
    
    result = []
    
    while heap:
        # Pop node with smallest lexical value among zero in-degree nodes
        node = heapq.heappop(heap)
        result.append(node)
        
        # Decrease in-degree of neighbors
        for neighbor in adjacency[node]:
            in_degrees[neighbor] -= 1
            if in_degrees[neighbor] == 0:
                heapq.heappush(heap, neighbor)
    
    # If not all nodes processed, there's a cycle
    if len(result) != len(_nodes):
        return []
    
    return result