import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class ASTSignature:
    name: str
    qualified_name: str
    kind: Literal["function", "class", "method"]
    line_start: int
    line_end: int
    parameters: list[str]
    return_annotation: str
    source_file: Path

    def format_compact(self) -> str:
        params = ", ".join(self.parameters)
        ret = f" -> {self.return_annotation}" if self.return_annotation else ""
        return f"{self.qualified_name}({params}){ret}  # {self.source_file}:{self.line_start}"


@dataclass
class FileSignatures:
    file_path: Path
    signatures: list[ASTSignature] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


@dataclass
class ContextMap:
    files: dict[Path, FileSignatures] = field(default_factory=dict)

    def all_signatures(self) -> list[ASTSignature]:
        return [sig for fs in self.files.values() for sig in fs.signatures]

    def nodes_relevant_to(self, test_ids: list[str]) -> list[ASTSignature]:
        """Return signatures referenced by the given pytest test node IDs."""
        if not test_ids:
            return []
        referenced = self._names_referenced_by_tests(test_ids)
        return [sig for sig in self.all_signatures() if sig.name in referenced]

    def _names_referenced_by_tests(self, test_ids: list[str]) -> set[str]:
        # Group test function names by file path
        test_files: dict[Path, set[str]] = {}
        for test_id in test_ids:
            parts = test_id.split("::")
            file_path = Path(parts[0])
            func_names = {p for p in parts[1:] if p.startswith("test_")}
            test_files.setdefault(file_path, set()).update(func_names)

        names: set[str] = set()
        for file_path, func_names in test_files.items():
            if not file_path.exists():
                continue
            try:
                tree = ast.parse(file_path.read_text())
            except (SyntaxError, OSError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not func_names or node.name in func_names:
                        names.update(_names_in_subtree(node))
        return names


class ContextMapBuilder:
    def build(self, files: list[Path]) -> ContextMap:
        cm = ContextMap()
        for file_path in files:
            file_path = Path(file_path)
            if not file_path.exists():
                continue
            cm.files[file_path] = self._parse_file(file_path)
        return cm

    def _parse_file(self, file_path: Path) -> FileSignatures:
        fs = FileSignatures(file_path=file_path)
        try:
            tree = ast.parse(file_path.read_text())
        except (SyntaxError, OSError):
            return fs

        fs.imports = _extract_imports(tree)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fs.signatures.append(_function_sig(node, file_path, prefix=""))
            elif isinstance(node, ast.ClassDef):
                fs.signatures.append(_class_sig(node, file_path))
                for item in ast.iter_child_nodes(node):
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        fs.signatures.append(_function_sig(item, file_path, prefix=f"{node.name}."))

        return fs


# --- helpers ---

def _function_sig(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    file_path: Path,
    prefix: str,
) -> ASTSignature:
    kind: Literal["function", "method"] = "method" if prefix else "function"
    return ASTSignature(
        name=node.name,
        qualified_name=f"{prefix}{node.name}",
        kind=kind,
        line_start=node.lineno,
        line_end=node.end_lineno or node.lineno,
        parameters=_format_params(node.args),
        return_annotation=_unparse(node.returns),
        source_file=file_path,
    )


def _class_sig(node: ast.ClassDef, file_path: Path) -> ASTSignature:
    return ASTSignature(
        name=node.name,
        qualified_name=node.name,
        kind="class",
        line_start=node.lineno,
        line_end=node.end_lineno or node.lineno,
        parameters=[_unparse(b) for b in node.bases],
        return_annotation="",
        source_file=file_path,
    )


def _format_params(args: ast.arguments) -> list[str]:
    params = []
    all_args = args.args
    defaults_offset = len(all_args) - len(args.defaults)

    for i, arg in enumerate(all_args):
        annotation = _unparse(arg.annotation)
        default_idx = i - defaults_offset
        if default_idx >= 0:
            default = ast.unparse(args.defaults[default_idx])
            params.append(f"{arg.arg}: {annotation} = {default}" if annotation else f"{arg.arg}={default}")
        else:
            params.append(f"{arg.arg}: {annotation}" if annotation else arg.arg)

    if args.vararg:
        ann = _unparse(args.vararg.annotation)
        params.append(f"*{args.vararg.arg}: {ann}" if ann else f"*{args.vararg.arg}")

    if args.kwarg:
        ann = _unparse(args.kwarg.annotation)
        params.append(f"**{args.kwarg.arg}: {ann}" if ann else f"**{args.kwarg.arg}")

    return params


def _extract_imports(tree: ast.Module) -> list[str]:
    imports = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(alias.asname or f"{module}.{alias.name}")
    return imports


def _names_in_subtree(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def _unparse(node: ast.expr | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""
