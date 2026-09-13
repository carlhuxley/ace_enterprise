"""
dependency_graph.py — a deterministic, persisted map of ace_enterprise's
own internal module dependencies, derived from real AST-parsed import
statements.

This is deliberately not persistent_dag.py's design (see the
fixture/dag-synthesis-artifacts branch, kept unmerged as reference output,
not shipped code): that manifest is *self-reported* -- modules explicitly
call register_module() to declare their own provides/depends_on, meant for
ACE's own multi-module builder to track modules it is actively
constructing. This module is the other half: *observed*, not declared --
it reads real import statements from real files, so it can describe an
existing codebase (starting with ace_enterprise's own src/ tree) rather
than a build plan.

Consequence of that difference: a cycle here is a fact about the existing
codebase, not a planning error, so has_cycle()/scan() never raise -- they
report. (Contrast persistent_dag.py's register_module(), which raises
CircularDependencyError and refuses to write, appropriately, since a cycle
in a build plan really is an error to reject before building.)

Usage: see generate_dependency_graph.py at the repo root for the concrete
"scan ace_enterprise itself" entry point. This module is intentionally
scan-target-agnostic -- point it at src_root=Path("src") today, or at a
migrated project's own package tree later, without change.
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST_RELPATH = ".ace/architecture_graph.json"


@dataclass
class ModuleNode:
    """One scanned file. `path` and every entry in `depends_on` are posix
    paths relative to the repo root (e.g. "src/agents/podman_runner.py"),
    so they're stable dict keys and directly usable as file paths."""

    path: str
    provides: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class DependencyGraph:
    modules: dict[str, ModuleNode] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "modules": {
                path: {"provides": node.provides, "depends_on": node.depends_on}
                for path, node in sorted(self.modules.items())
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> DependencyGraph:
        modules = {
            path: ModuleNode(path=path, provides=list(v.get("provides", [])), depends_on=list(v.get("depends_on", [])))
            for path, v in data.get("modules", {}).items()
        }
        return cls(modules=modules)


def save(graph: DependencyGraph, path: Path = Path(MANIFEST_RELPATH)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph.to_dict(), indent=2) + "\n")


def load(path: Path = Path(MANIFEST_RELPATH)) -> DependencyGraph:
    if not path.exists():
        return DependencyGraph()
    return DependencyGraph.from_dict(json.loads(path.read_text()))


# --- scanning ---------------------------------------------------------

def scan(src_root: Path, repo_root: Path | None = None) -> DependencyGraph:
    """AST-scan every .py file under src_root; resolve each import against
    repo_root (default: src_root's parent) into another file under
    repo_root, discarding anything that isn't (stdlib, third-party,
    anything outside the scanned tree)."""
    repo_root = repo_root or src_root.parent
    graph = DependencyGraph()

    py_files = sorted(p for p in src_root.rglob("*.py") if not p.name.startswith("__pycache__"))
    for file_path in py_files:
        rel_path = file_path.relative_to(repo_root).as_posix()
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            graph.modules[rel_path] = ModuleNode(path=rel_path)
            continue

        graph.modules[rel_path] = ModuleNode(
            path=rel_path,
            provides=_public_names(tree),
            depends_on=sorted(_resolve_imports(tree, file_path, repo_root)),
        )

    return graph


def _public_names(tree: ast.Module) -> list[str]:
    """Top-level function/class names not starting with '_' -- this
    module's equivalent of persistent_dag.py's `provides`."""
    names = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            names.append(node.name)
    return names


def _module_to_relpath(dotted: str, repo_root: Path) -> str | None:
    """'src.agents.podman_runner' -> 'src/agents/podman_runner.py' if that
    file (or a package __init__.py at that path) actually exists under
    repo_root; None otherwise (stdlib, third-party, or just wrong)."""
    if not dotted:
        return None
    rel = dotted.replace(".", "/")
    candidate = repo_root / f"{rel}.py"
    if candidate.is_file():
        return candidate.relative_to(repo_root).as_posix()
    candidate = repo_root / rel / "__init__.py"
    if candidate.is_file():
        return candidate.relative_to(repo_root).as_posix()
    return None


def _resolve_imports(tree: ast.Module, file_path: Path, repo_root: Path) -> set[str]:
    resolved: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _module_to_relpath(alias.name, repo_root)
                if target:
                    resolved.add(target)
        elif isinstance(node, ast.ImportFrom):
            module = _from_import_module(node, file_path, repo_root)
            if not module:
                continue
            for alias in node.names:
                # Prefer treating the imported name as a submodule
                # (`from src.agents import podman_runner`); fall back to
                # treating it as a symbol defined inside `module` itself
                # (`from src.agents.podman_runner import PulseResult`).
                target = _module_to_relpath(f"{module}.{alias.name}", repo_root)
                if target is None:
                    target = _module_to_relpath(module, repo_root)
                if target:
                    resolved.add(target)
    resolved.discard(file_path.relative_to(repo_root).as_posix())  # no self-edges
    return resolved


def _from_import_module(node: ast.ImportFrom, file_path: Path, repo_root: Path) -> str:
    """The complete dotted module path a `from X import ...` statement
    names as X.

    Absolute (`from a.b.c import d`, level == 0): node.module IS that
    complete path already ("a.b.c") -- return it verbatim, nothing to
    join.

    Relative (`from .x import y` / `from ..x import y`, level > 0): walk
    up `level` package directories from this file's own package to find
    the base, then join node.module onto it (if there is one -- `from .
    import y` has node.module == None, i.e. the base itself is what's
    being imported from)."""
    if node.level == 0:
        return node.module or ""
    pkg_dir = file_path.parent
    for _ in range(node.level - 1):
        pkg_dir = pkg_dir.parent
    base = pkg_dir.relative_to(repo_root).as_posix().replace("/", ".")
    return f"{base}.{node.module}" if node.module else base


# --- graph algorithms ---------------------------------------------------

def has_cycle(graph: DependencyGraph) -> list[str] | None:
    """DFS-based cycle detection. Returns the cycle as a list of module
    paths if found, else None. Never raises: see module docstring."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(graph.modules, WHITE)
    path_stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = GRAY
        path_stack.append(node)
        for neighbor in graph.modules.get(node, ModuleNode(path=node)).depends_on:
            if neighbor not in color:
                continue  # dependency outside the scanned set
            if color[neighbor] == GRAY:
                cycle_start = path_stack.index(neighbor)
                return path_stack[cycle_start:] + [neighbor]
            if color[neighbor] == WHITE:
                found = dfs(neighbor)
                if found:
                    return found
        path_stack.pop()
        color[node] = BLACK
        return None

    for path in graph.modules:
        if color[path] == WHITE:
            found = dfs(path)
            if found:
                return found
    return None


def build_order(graph: DependencyGraph) -> list[str]:
    """Kahn's algorithm, lexical tie-break. Returns [] if the graph has a
    cycle -- call has_cycle() first for a diagnostic rather than treating
    an empty list as "zero modules"."""
    import heapq

    # in_degree[X] = number of modules X depends on that are also in the
    # scanned set (X must come after them in build order).
    in_degree = dict.fromkeys(graph.modules, 0)
    for node in graph.modules.values():
        for dep in node.depends_on:
            if dep in graph.modules:
                in_degree[node.path] += 1

    dependents: dict[str, list[str]] = {path: [] for path in graph.modules}
    for node in graph.modules.values():
        for dep in node.depends_on:
            if dep in graph.modules:
                dependents[dep].append(node.path)

    heap = sorted(path for path, deg in in_degree.items() if deg == 0)
    heapq.heapify(heap)
    order: list[str] = []
    while heap:
        node = heapq.heappop(heap)
        order.append(node)
        for dependent in sorted(dependents[node]):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                heapq.heappush(heap, dependent)

    return order if len(order) == len(graph.modules) else []


def blast_radius(graph: DependencyGraph, module_path: str) -> set[str]:
    """`module_path` plus every module that transitively depends on it
    (all downstream dependents) -- "if I change this, what else needs
    re-checking."""
    dependents: dict[str, list[str]] = {path: [] for path in graph.modules}
    for node in graph.modules.values():
        for dep in node.depends_on:
            if dep in dependents:
                dependents[dep].append(node.path)

    radius = {module_path}
    queue = [module_path]
    while queue:
        current = queue.pop()
        for dependent in dependents.get(current, []):
            if dependent not in radius:
                radius.add(dependent)
                queue.append(dependent)
    return radius


# --- rendering ------------------------------------------------------------

def to_mermaid_flowchart(graph: DependencyGraph) -> str:
    """Render as a mermaid flowchart -- deliberately not a sequenceDiagram:
    flowchart syntax has no activate/deactivate pairing to get wrong (see
    the SYSTEM_ARCHITECTURE.md mermaid fix this graph is partly motivated
    by)."""
    lines = ["flowchart TD"]
    ids = {path: f"n{i}" for i, path in enumerate(sorted(graph.modules))}
    for path, node_id in ids.items():
        label = Path(path).stem
        lines.append(f'    {node_id}["{label}"]')
    for path, node in sorted(graph.modules.items()):
        for dep in sorted(node.depends_on):
            if dep in ids:
                lines.append(f"    {ids[path]} --> {ids[dep]}")
    return "\n".join(lines)
