"""Stage 3 — Clean-room gate.

Checks that a synthesized file does not contain internal implementation
identifiers from the private source tree. Public API names (intended to
match) are excluded; only underscore-prefixed private names are checked.

Also checks docstring token overlap as a secondary signal.
"""
import ast
from pathlib import Path

_NAME_OVERLAP_THRESHOLD = 0.35
_DOCWORD_THRESHOLD = 0.60

_STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "is", "are", "was", "were", "be", "been",
    "to", "of", "in", "for", "with", "on", "at", "by", "from", "as", "this",
    "that", "it", "not", "no", "if", "else", "return", "def", "class",
    "import", "true", "false", "none", "self", "args", "kwargs", "str",
    "int", "bool", "list", "dict", "optional", "none", "value", "result",
    "error", "output", "input", "param", "type", "raises",
})


def _private_function_names(tree: ast.AST) -> set[str]:
    """Return underscore-prefixed function/method names — definitionally internal."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and node.name not in ("__init__", "__repr__", "__str__"):
                names.add(node.name)
    return names


def _docstring_tokens(tree: ast.AST) -> set[str]:
    tokens: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            val = node.value.value
            if isinstance(val, str) and len(val) > 30:
                tokens.update(w.strip(".,;:()[]") for w in val.lower().split())
    return tokens - _STOP_WORDS


def verify_clean_room(synthesized_path: Path, private_src_root: Path) -> list[str]:
    """Return list of violation strings; empty list means clean.

    Checks synthesized_path against every .py file under private_src_root.
    """
    try:
        synth_tree = ast.parse(synthesized_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    synth_privates = _private_function_names(synth_tree)
    synth_docwords = _docstring_tokens(synth_tree)

    violations: list[str] = []

    for private_file in sorted(private_src_root.rglob("*.py")):
        try:
            private_tree = ast.parse(private_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        # Check 1: private function name overlap
        if synth_privates:
            private_privates = _private_function_names(private_tree)
            overlap = synth_privates & private_privates
            ratio = len(overlap) / len(synth_privates)
            if ratio > _NAME_OVERLAP_THRESHOLD:
                violations.append(
                    f"private-name overlap {ratio:.0%} with {private_file.name}: "
                    + ", ".join(sorted(overlap))
                )

        # Check 2: docstring token overlap
        if len(synth_docwords) >= 10:
            private_docwords = _docstring_tokens(private_tree)
            if private_docwords:
                shared = synth_docwords & private_docwords
                ratio = len(shared) / len(synth_docwords)
                if ratio > _DOCWORD_THRESHOLD:
                    violations.append(
                        f"docstring token overlap {ratio:.0%} with {private_file.name}"
                    )

    return violations
