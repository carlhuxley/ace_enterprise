"""Deterministic topological ordering with a lexical tie-break.

Used to order a directory of `.feature` files for `ace tdd` and the modules
in a `ProjectPlan` for `ace project` -- both need "build dependencies first,
otherwise alphabetical" plus clear errors on an unknown reference or a cycle.
"""

from __future__ import annotations


class DependencyError(ValueError):
    """A dependency graph that can't be ordered (unknown ref or a cycle)."""


def topo_order(nodes: list[str], deps: dict[str, list[str]]) -> list[str]:
    """Return `nodes` ordered so every node follows the nodes it depends on.

    Args:
        nodes: the full set of node names (order here is the tie-break order
            when several nodes are ready at once -- pass it pre-sorted for a
            lexical result).
        deps: node -> list of nodes it must come after. Nodes absent from the
            mapping (or with an empty list) have no dependencies.

    Raises:
        DependencyError: a dependency names an unknown node, or the graph
            has a cycle.
    """
    node_set = set(nodes)
    for node, requires in deps.items():
        if node not in node_set:
            raise DependencyError(f"dependency declared for unknown node {node!r}")
        for req in requires:
            if req not in node_set:
                raise DependencyError(f"{node!r} depends on unknown node {req!r}")

    remaining = {n: set(deps.get(n, ())) for n in nodes}
    ordered: list[str] = []
    while remaining:
        ready = sorted(n for n, r in remaining.items() if not r)
        if not ready:
            cycle = ", ".join(sorted(remaining))
            raise DependencyError(f"dependency cycle among: {cycle}")
        for n in ready:
            ordered.append(n)
            del remaining[n]
        for r in remaining.values():
            r.difference_update(ready)
    return ordered
