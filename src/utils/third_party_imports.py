"""Infer third-party (non-stdlib, non-local) packages referenced by generated
Python code, so the sandbox can install what a module actually needs (#53)
instead of only ever offering the stdlib.

Deliberately AST-based, not a declared field on any contract — mirrors the
existing `_undeclared_sibling_deps` pattern in `src/cli/project_builder.py`
(#30): trust what the generated code actually imports over what a plan or
contract predicted it would need, since either can be under- or
over-specified and the code is the ground truth of what must be installed
for it to run.
"""

from __future__ import annotations

import ast
import sys

_STDLIB_NAMES = frozenset(getattr(sys, "stdlib_module_names", ()))

# Import name -> PyPI distribution name, for the common cases where they
# differ. Best-effort, not exhaustive -- an unlisted import is assumed to
# share its PyPI name (true for the large majority of packages, including
# flask, gradio, requests, numpy, pandas, click, pydantic, fastapi).
_IMPORT_TO_PACKAGE = {
    "yaml": "PyYAML",
    "PIL": "Pillow",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "dotenv": "python-dotenv",
    "jwt": "PyJWT",
}


def infer_third_party_packages(
    code_blobs: list[str], *, known_local_names: set[str] | None = None
) -> frozenset[str]:
    """Top-level `import` / `from ... import` targets across `code_blobs`
    that are neither stdlib nor one of `known_local_names` (sibling/own
    module stems already present in the sandbox), mapped to PyPI
    distribution names. Unparseable blobs are skipped, not raised -- this
    is a best-effort hint for what to install, not a correctness gate.
    """
    local = known_local_names or set()
    found: set[str] = set()
    for code in code_blobs:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found |= {a.name.partition(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module.partition(".")[0])

    third_party = found - _STDLIB_NAMES - local
    return frozenset(_IMPORT_TO_PACKAGE.get(name, name) for name in third_party)
