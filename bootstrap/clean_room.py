"""Stage 3 — Clean-room gate.

Two verification paths:

  verify_clean_room()               — same-language (Python → Python)
    Check 1: private function name overlap (AST-based)
    Check 2: docstring N-gram token overlap

  verify_clean_room_cross_language() — cross-language (Python → TypeScript)
    Guard A: high-entropy semantic token overlap
              Normalise snake_case ↔ camelCase identifiers to a canonical word
              sequence and look for matching business-logic names that survived
              the Gherkin translation. A uniquely named internal identifier like
              delta_calculation_accumulator_buffer matching
              deltaCalculationAccumulatorBuffer is a structural lineage signal.
    Guard B: JSDoc / docstring N-gram token overlap (same as same-language Check 2)

Both paths return a CleanRoomResult so the caller can log explicit overlap
percentages in audit.jsonl rather than a bare pass/fail.
"""
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

# --- thresholds ----------------------------------------------------------

_SAME_LANG_NAME_THRESHOLD = 0.35    # fraction of private names that may overlap
_CROSS_LANG_SEMANTIC_THRESHOLD = 0.10  # Guard A: fraction of high-entropy names
_DOCWORD_THRESHOLD = 0.60           # Guard B / Check 2: JSDoc token fraction

# --- stop-word sets -------------------------------------------------------

_DOCWORD_STOP = frozenset({
    "the", "a", "an", "and", "or", "is", "are", "was", "were", "be", "been",
    "to", "of", "in", "for", "with", "on", "at", "by", "from", "as", "this",
    "that", "it", "not", "no", "if", "else", "return", "def", "class",
    "import", "true", "false", "none", "self", "args", "kwargs", "str",
    "int", "bool", "list", "dict", "optional", "value", "result",
    "error", "output", "input", "param", "type", "raises",
})

# Common single-word programming identifiers that carry no domain signal
_SEMANTIC_STOP = frozenset({
    "get", "set", "is", "has", "can", "will", "to", "from", "with",
    "value", "result", "output", "input", "data", "item", "items",
    "list", "dict", "map", "key", "val", "run", "start", "stop",
    "init", "update", "reset", "clear", "add", "remove", "delete",
    "create", "build", "parse", "format", "check", "validate",
    "handle", "process", "test", "spec", "error", "message", "code",
    "type", "name", "id", "index", "count", "size", "length",
    "config", "options", "params", "args", "client", "server",
    "request", "response", "path", "file", "string", "number",
    "boolean", "object", "node", "tree", "root", "child", "parent",
})

_TS_KEYWORDS = frozenset({
    "const", "let", "var", "function", "class", "interface", "type",
    "import", "export", "from", "return", "if", "else", "for", "while",
    "true", "false", "null", "undefined", "void", "string", "number",
    "boolean", "any", "never", "this", "new", "extends", "implements",
    "readonly", "private", "public", "protected", "static", "async",
    "await", "try", "catch", "throw", "default", "switch", "case",
    "break", "continue", "typeof", "instanceof", "describe", "it",
    "test", "expect", "beforeEach", "afterEach", "of", "in",
})


# --- result type ---------------------------------------------------------

@dataclass
class CleanRoomResult:
    passed: bool
    violations: list[str] = field(default_factory=list)
    structural_overlap: float = 0.0   # Guard A ratio (cross-lang) or private name overlap
    docword_overlap: float = 0.0      # Guard B ratio
    checks_run: list[str] = field(default_factory=list)

    def as_log_payload(
        self,
        module: str,
        input_language: str = "Python (Source AST)",
        output_language: str = "Python (Target AST)",
    ) -> dict:
        return {
            "module": module,
            "input_language": input_language,
            "output_language": output_language,
            "metrics": {
                "structural_lineage_overlap": f"{self.structural_overlap:.2%}",
                "jsdoc_token_overlap": f"{self.docword_overlap:.2%}",
            },
            "checks_run": self.checks_run,
            "violations": self.violations,
        }


# --- helpers -------------------------------------------------------------

def _private_function_names(tree: ast.AST) -> set[str]:
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
                tokens.update(w.strip(".,;:()[]\"'") for w in val.lower().split())
    return tokens - _DOCWORD_STOP


def _ts_comment_tokens(code: str) -> set[str]:
    """Extract tokens from TypeScript // line comments and /** JSDoc */ blocks."""
    raw: list[str] = []
    for m in re.finditer(r"//(.+)|/\*\*(.*?)\*/", code, re.DOTALL):
        raw.append(m.group(1) or m.group(2) or "")
    text = " ".join(raw)
    tokens = {w.strip(".,;:()[]\"'*@") for w in text.lower().split()}
    return tokens - _DOCWORD_STOP


def _split_identifier(name: str) -> list[str]:
    """Split snake_case or camelCase/PascalCase into lowercase words."""
    # Handle acronyms: HTTPSClient → HTTPS_Client
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    # Insert boundary before each uppercase letter
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return [w.lower() for w in re.split(r"[_\W]+", name) if w and len(w) > 1]


def _canonical_key(words: list[str]) -> str:
    return "".join(words)


def _is_high_entropy(words: list[str]) -> bool:
    """True if the identifier carries real domain signal (not just common words)."""
    if len(words) < 3:
        return False
    domain_words = [w for w in words if w not in _SEMANTIC_STOP and len(w) > 3]
    return len(domain_words) >= 2


def _python_high_entropy_identifiers(src_root: Path) -> set[str]:
    """Extract canonical keys of all high-entropy identifiers from the private source tree."""
    keys: set[str] = set()
    for py_file in sorted(src_root.rglob("*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            name: str | None = None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name
            elif isinstance(node, ast.Name):
                name = node.id
            if name:
                words = _split_identifier(name)
                if _is_high_entropy(words):
                    keys.add(_canonical_key(words))
    return keys


def _ts_high_entropy_identifiers(code: str) -> set[str]:
    """Extract canonical keys of high-entropy identifiers from TypeScript source text."""
    raw = re.findall(r"\b[a-zA-Z_$][a-zA-Z0-9_$]{3,}\b", code)
    keys: set[str] = set()
    for name in raw:
        if name in _TS_KEYWORDS:
            continue
        words = _split_identifier(name)
        if _is_high_entropy(words):
            keys.add(_canonical_key(words))
    return keys


# --- public API ----------------------------------------------------------

def verify_clean_room(synthesized_path: Path, private_src_root: Path) -> CleanRoomResult:
    """Same-language (Python → Python) clean-room check."""
    try:
        synth_tree = ast.parse(synthesized_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return CleanRoomResult(passed=True, checks_run=["syntax_error_skip"])

    synth_privates = _private_function_names(synth_tree)
    synth_docwords = _docstring_tokens(synth_tree)

    violations: list[str] = []
    max_name_ratio = 0.0
    max_doc_ratio = 0.0

    for private_file in sorted(private_src_root.rglob("*.py")):
        try:
            private_tree = ast.parse(private_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        if synth_privates:
            overlap = synth_privates & _private_function_names(private_tree)
            ratio = len(overlap) / len(synth_privates)
            max_name_ratio = max(max_name_ratio, ratio)
            if ratio > _SAME_LANG_NAME_THRESHOLD:
                violations.append(
                    f"private-name overlap {ratio:.0%} with {private_file.name}: "
                    + ", ".join(sorted(overlap))
                )

        if len(synth_docwords) >= 10:
            private_docwords = _docstring_tokens(private_tree)
            if private_docwords:
                shared = synth_docwords & private_docwords
                ratio = len(shared) / len(synth_docwords)
                max_doc_ratio = max(max_doc_ratio, ratio)
                if ratio > _DOCWORD_THRESHOLD:
                    violations.append(
                        f"docstring token overlap {ratio:.0%} with {private_file.name}"
                    )

    return CleanRoomResult(
        passed=len(violations) == 0,
        violations=violations,
        structural_overlap=max_name_ratio,
        docword_overlap=max_doc_ratio,
        checks_run=["private_function_names", "docstring_tokens"],
    )


def verify_clean_room_cross_language(
    synthesized_path: Path,
    private_src_root: Path,
) -> CleanRoomResult:
    """Cross-language (Python → TypeScript) clean-room check.

    Guard A — high-entropy semantic token overlap:
        Normalise all Python and TypeScript identifiers to a canonical word
        sequence (stripping snake_case / camelCase casing). Flag if a
        significant fraction of the private tree's high-entropy identifiers
        appear verbatim in the synthesised output.

    Guard B — JSDoc / docstring N-gram token overlap:
        Compare TypeScript comment/JSDoc tokens against Python docstring tokens.
        A ratio above _DOCWORD_THRESHOLD indicates verbatim commentary leakage.
    """
    ts_code = synthesized_path.read_text(encoding="utf-8")

    # Guard A
    private_he_keys = _python_high_entropy_identifiers(private_src_root)
    synth_he_keys = _ts_high_entropy_identifiers(ts_code)

    semantic_overlap_keys: set[str] = set()
    semantic_ratio = 0.0
    if private_he_keys:
        semantic_overlap_keys = private_he_keys & synth_he_keys
        semantic_ratio = len(semantic_overlap_keys) / len(private_he_keys)

    # Guard B
    synth_comment_tokens = _ts_comment_tokens(ts_code)
    max_doc_ratio = 0.0
    doc_violation_files: list[str] = []

    for private_file in sorted(private_src_root.rglob("*.py")):
        try:
            private_tree = ast.parse(private_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        if len(synth_comment_tokens) >= 10:
            private_docwords = _docstring_tokens(private_tree)
            if private_docwords:
                shared = synth_comment_tokens & private_docwords
                ratio = len(shared) / len(synth_comment_tokens)
                if ratio > max_doc_ratio:
                    max_doc_ratio = ratio
                if ratio > _DOCWORD_THRESHOLD:
                    doc_violation_files.append(f"{private_file.name} ({ratio:.0%})")

    violations: list[str] = []
    if semantic_ratio > _CROSS_LANG_SEMANTIC_THRESHOLD:
        violations.append(
            f"Guard A — semantic overlap {semantic_ratio:.2%} "
            f"({len(semantic_overlap_keys)} high-entropy keys matched): "
            + ", ".join(sorted(semantic_overlap_keys)[:10])
        )
    for v in doc_violation_files:
        violations.append(f"Guard B — JSDoc token overlap with {v}")

    return CleanRoomResult(
        passed=len(violations) == 0,
        violations=violations,
        structural_overlap=semantic_ratio,
        docword_overlap=max_doc_ratio,
        checks_run=["guard_a_semantic_token_overlap", "guard_b_jsdoc_ngram"],
    )
