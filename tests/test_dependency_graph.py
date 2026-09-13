"""Tests for dependency_graph.py — the *observed* (AST-derived) counterpart
to persistent_dag.py's *declared* (self-reported) manifest design.

Fixture directories are built under tmp_path so scan() runs against real
files, not mocked ASTs -- import resolution is exactly the kind of thing
that looks right by inspection and is wrong in a specific case (relative
imports, package-vs-symbol ambiguity) if not actually exercised.
"""
import json
from pathlib import Path

from src.utils.dependency_graph import (
    DependencyGraph,
    ModuleNode,
    blast_radius,
    build_order,
    has_cycle,
    load,
    save,
    scan,
    to_mermaid_flowchart,
)


def _write(root: Path, rel_path: str, content: str) -> None:
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


# ---------------------------------------------------------------------------
# scan() / import resolution
# ---------------------------------------------------------------------------

def test_absolute_from_import_symbol_in_module(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "def foo(): pass\n")
    _write(tmp_path, "pkg/b.py", "from pkg.a import foo\n")

    graph = scan(tmp_path / "pkg", repo_root=tmp_path)
    assert graph.modules["pkg/b.py"].depends_on == ["pkg/a.py"]


def test_absolute_from_import_submodule(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "def foo(): pass\n")
    _write(tmp_path, "pkg/b.py", "from pkg import a\n")

    graph = scan(tmp_path / "pkg", repo_root=tmp_path)
    assert graph.modules["pkg/b.py"].depends_on == ["pkg/a.py"]


def test_plain_import_statement(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "def foo(): pass\n")
    _write(tmp_path, "pkg/b.py", "import pkg.a\n")

    graph = scan(tmp_path / "pkg", repo_root=tmp_path)
    assert graph.modules["pkg/b.py"].depends_on == ["pkg/a.py"]


def test_relative_import_same_package(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "def foo(): pass\n")
    _write(tmp_path, "pkg/b.py", "from .a import foo\n")

    graph = scan(tmp_path / "pkg", repo_root=tmp_path)
    assert graph.modules["pkg/b.py"].depends_on == ["pkg/a.py"]


def test_relative_import_parent_package(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "def foo(): pass\n")
    _write(tmp_path, "pkg/sub/__init__.py", "")
    _write(tmp_path, "pkg/sub/b.py", "from ..a import foo\n")

    graph = scan(tmp_path / "pkg", repo_root=tmp_path)
    assert graph.modules["pkg/sub/b.py"].depends_on == ["pkg/a.py"]


def test_external_and_stdlib_imports_discarded(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "import os\nimport numpy as np\nfrom pathlib import Path\n")

    graph = scan(tmp_path / "pkg", repo_root=tmp_path)
    assert graph.modules["pkg/a.py"].depends_on == []


def test_no_self_edges(tmp_path):
    # A module importing a name from itself via its own dotted path
    # shouldn't create a self-referential edge.
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "X = 1\nfrom pkg.a import X as X2\n")

    graph = scan(tmp_path / "pkg", repo_root=tmp_path)
    assert "pkg/a.py" not in graph.modules["pkg/a.py"].depends_on


def test_provides_captures_public_top_level_names_only(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path, "pkg/a.py",
        "def public_fn(): pass\n"
        "def _private_fn(): pass\n"
        "class PublicClass: pass\n"
    )

    graph = scan(tmp_path / "pkg", repo_root=tmp_path)
    assert graph.modules["pkg/a.py"].provides == ["public_fn", "PublicClass"]


def test_syntax_error_file_is_recorded_but_inert(tmp_path):
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/broken.py", "def f(:\n")

    graph = scan(tmp_path / "pkg", repo_root=tmp_path)
    assert graph.modules["pkg/broken.py"].provides == []
    assert graph.modules["pkg/broken.py"].depends_on == []


# ---------------------------------------------------------------------------
# graph algorithms
# ---------------------------------------------------------------------------

def _graph(edges: dict[str, list[str]]) -> DependencyGraph:
    return DependencyGraph(modules={k: ModuleNode(path=k, depends_on=v) for k, v in edges.items()})


def test_has_cycle_detects_a_real_cycle():
    graph = _graph({"a.py": ["b.py"], "b.py": ["c.py"], "c.py": ["a.py"]})
    cycle = has_cycle(graph)
    assert cycle is not None
    assert set(cycle) == {"a.py", "b.py", "c.py"}


def test_has_cycle_returns_none_for_a_dag():
    graph = _graph({"a.py": ["b.py"], "b.py": ["c.py"], "c.py": []})
    assert has_cycle(graph) is None


def test_build_order_respects_dependencies_and_lexical_tie_break():
    # b and c both only depend on a -- tie-break must pick b before c.
    graph = _graph({"a.py": [], "b.py": ["a.py"], "c.py": ["a.py"]})
    assert build_order(graph) == ["a.py", "b.py", "c.py"]


def test_build_order_empty_for_a_cyclic_graph():
    graph = _graph({"a.py": ["b.py"], "b.py": ["a.py"]})
    assert build_order(graph) == []


def test_blast_radius_includes_self_and_transitive_dependents():
    # a <- b <- c  (c depends on b depends on a)
    graph = _graph({"a.py": [], "b.py": ["a.py"], "c.py": ["b.py"], "unrelated.py": []})
    assert blast_radius(graph, "a.py") == {"a.py", "b.py", "c.py"}
    assert blast_radius(graph, "c.py") == {"c.py"}


def test_dependency_outside_scanned_set_is_ignored_by_algorithms():
    # b.py "depends on" something not in the scanned graph at all --
    # should not blow up has_cycle/build_order/blast_radius.
    graph = _graph({"a.py": ["ghost.py"], "b.py": ["a.py"]})
    assert has_cycle(graph) is None
    assert build_order(graph) == ["a.py", "b.py"]
    assert blast_radius(graph, "a.py") == {"a.py", "b.py"}


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------

def test_save_and_load_round_trip(tmp_path):
    graph = _graph({"a.py": [], "b.py": ["a.py"]})
    graph.modules["a.py"].provides = ["foo"]
    manifest_path = tmp_path / ".ace" / "architecture_graph.json"

    save(graph, manifest_path)
    reloaded = load(manifest_path)

    assert reloaded.modules["a.py"].provides == ["foo"]
    assert reloaded.modules["b.py"].depends_on == ["a.py"]


def test_load_missing_file_returns_empty_graph(tmp_path):
    graph = load(tmp_path / "does_not_exist.json")
    assert graph.modules == {}


def test_saved_manifest_is_readable_json(tmp_path):
    graph = _graph({"a.py": [], "b.py": ["a.py"]})
    manifest_path = tmp_path / "graph.json"
    save(graph, manifest_path)

    data = json.loads(manifest_path.read_text())
    assert data["modules"]["b.py"]["depends_on"] == ["a.py"]


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def test_mermaid_flowchart_contains_every_node_and_edge():
    graph = _graph({"a.py": [], "b.py": ["a.py"]})
    rendered = to_mermaid_flowchart(graph)

    assert rendered.startswith("flowchart TD")
    assert '"a"' in rendered
    assert '"b"' in rendered
    assert "-->" in rendered
