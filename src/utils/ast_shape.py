"""AST-level "protected shape" extraction and comparison.

Used to lock a pre-scaffolded module's type-level "corners" (class bases/
decorators, dataclass fields, method/function signatures, constants, type
aliases) against being silently rewritten by `--diff-editing`'s SEARCH/
REPLACE patching -- the LLM may fill in or change a protected method's BODY
freely, and may add entirely new classes/functions/methods, but may not
change the recorded shape of a symbol that was already there when the shape
was captured.

No LLM involvement here, same house style as `src/utils/patcher.py` (which
this module has no dependency on -- `patcher.py` imports FROM here, not the
other way, keeping `src/utils/*` a self-contained layer beneath
`src/contracts/*`).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldShape:
    annotation: str
    default: str | None


@dataclass(frozen=True)
class MethodShape:
    args: str
    returns: str
    is_property: bool


@dataclass(frozen=True)
class ConstantShape:
    annotation: str
    value: str | None


@dataclass(frozen=True)
class ImportShape:
    """One top-level `import`/`from ... import ...` binding, keyed by the
    LOCAL name it binds (its own `as` alias, if any). `imported_name` is
    None for a plain `import module` statement (the whole module is bound),
    or the original name for `from module import name[ as local]`."""

    module: str
    imported_name: str | None


@dataclass(frozen=True)
class ClassShape:
    bases: frozenset[str]
    decorators: frozenset[str]
    fields: dict[str, FieldShape] = field(default_factory=dict)
    methods: dict[str, MethodShape] = field(default_factory=dict)


@dataclass(frozen=True)
class ProtectedShape:
    classes: dict[str, ClassShape] = field(default_factory=dict)
    functions: dict[str, MethodShape] = field(default_factory=dict)
    constants: dict[str, ConstantShape] = field(default_factory=dict)
    type_aliases: dict[str, str] = field(default_factory=dict)
    imports: dict[str, ImportShape] = field(default_factory=dict)


def _unparse(node: ast.AST) -> str:
    return ast.unparse(node)


def _is_property(decorators: frozenset[str]) -> bool:
    return "property" in decorators


def _function_shape(node: ast.FunctionDef | ast.AsyncFunctionDef) -> MethodShape:
    decorators = frozenset(_unparse(d) for d in node.decorator_list)
    returns = _unparse(node.returns) if node.returns is not None else ""
    return MethodShape(args=_unparse(node.args), returns=returns, is_property=_is_property(decorators))


def _class_shape(node: ast.ClassDef) -> ClassShape:
    bases = frozenset(_unparse(b) for b in node.bases)
    decorators = frozenset(_unparse(d) for d in node.decorator_list)
    fields: dict[str, FieldShape] = {}
    methods: dict[str, MethodShape] = {}
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            annotation = _unparse(stmt.annotation)
            default = _unparse(stmt.value) if stmt.value is not None else None
            fields[stmt.target.id] = FieldShape(annotation=annotation, default=default)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods[stmt.name] = _function_shape(stmt)
    return ClassShape(bases=bases, decorators=decorators, fields=fields, methods=methods)


def extract_protected_shape(source: str) -> ProtectedShape:
    """One `ast.parse` + top-level walk of `source`, recording every
    module-level class (bases, decorators, `AnnAssign` fields, methods),
    module-level function, module-level constant (`AnnAssign`), module-level
    type alias (plain `name = <expr>` assignment), and module-level import
    (`import ...`/`from ... import ...`, one entry per locally-bound name).
    Nested/non-top-level statements are not inspected -- a scaffold's own
    protected symbols, including the cross-module imports
    `module_contract_scaffold.scaffold_module` injects for a `depends_on`
    entry, are always top-level; wrapping one in a nested `try/except` (or
    any other conditional) to dodge this check is itself the violation this
    is meant to catch."""
    tree = ast.parse(source)
    shape = ProtectedShape()
    for stmt in tree.body:
        if isinstance(stmt, ast.ClassDef):
            shape.classes[stmt.name] = _class_shape(stmt)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            shape.functions[stmt.name] = _function_shape(stmt)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            annotation = _unparse(stmt.annotation)
            value = _unparse(stmt.value) if stmt.value is not None else None
            shape.constants[stmt.target.id] = ConstantShape(annotation=annotation, value=value)
        elif (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            shape.type_aliases[stmt.targets[0].id] = _unparse(stmt.value)
        elif isinstance(stmt, ast.ImportFrom):
            module = "." * stmt.level + (stmt.module or "")
            for alias in stmt.names:
                local_name = alias.asname or alias.name
                shape.imports[local_name] = ImportShape(module=module, imported_name=alias.name)
        elif isinstance(stmt, ast.Import):
            for alias in stmt.names:
                local_name = alias.asname or alias.name.split(".")[0]
                shape.imports[local_name] = ImportShape(module=alias.name, imported_name=None)
    return shape


def diff_protected_shapes(before: ProtectedShape, after: ProtectedShape) -> list[str]:
    """Every way `after` fails to preserve a symbol recorded in `before`.
    Empty means fully compatible. Symbols in `after` but not `before`
    (the LLM adding new classes/functions/methods) are never a violation --
    only a symbol from `before` being removed or reshaped is."""
    violations: list[str] = []

    for name, before_class in before.classes.items():
        after_class = after.classes.get(name)
        if after_class is None:
            violations.append(f"class {name!r} was removed")
            continue
        if before_class.bases != after_class.bases:
            violations.append(
                f"class {name!r} bases changed from {sorted(before_class.bases)} "
                f"to {sorted(after_class.bases)}"
            )
        if before_class.decorators != after_class.decorators:
            violations.append(
                f"class {name!r} decorators changed from {sorted(before_class.decorators)} "
                f"to {sorted(after_class.decorators)}"
            )
        for field_name, before_field in before_class.fields.items():
            after_field = after_class.fields.get(field_name)
            if after_field is None:
                violations.append(f"class {name!r}: field {field_name!r} was removed")
            elif after_field != before_field:
                violations.append(
                    f"class {name!r}: field {field_name!r} changed from "
                    f"{before_field.annotation!r}={before_field.default!r} to "
                    f"{after_field.annotation!r}={after_field.default!r}"
                )
        for method_name, before_method in before_class.methods.items():
            after_method = after_class.methods.get(method_name)
            if after_method is None:
                violations.append(f"class {name!r}: method {method_name!r} was removed")
            elif after_method != before_method:
                violations.append(
                    f"class {name!r}: method {method_name!r} signature changed from "
                    f"({before_method.args}) -> {before_method.returns} to "
                    f"({after_method.args}) -> {after_method.returns}"
                )

    for name, before_fn in before.functions.items():
        after_fn = after.functions.get(name)
        if after_fn is None:
            violations.append(f"function {name!r} was removed")
        elif after_fn != before_fn:
            violations.append(
                f"function {name!r} signature changed from ({before_fn.args}) -> "
                f"{before_fn.returns} to ({after_fn.args}) -> {after_fn.returns}"
            )

    for name, before_const in before.constants.items():
        after_const = after.constants.get(name)
        if after_const is None:
            violations.append(f"constant {name!r} was removed")
        elif after_const != before_const:
            violations.append(
                f"constant {name!r} changed from {before_const.annotation!r}="
                f"{before_const.value!r} to {after_const.annotation!r}={after_const.value!r}"
            )

    for name, before_def in before.type_aliases.items():
        after_def = after.type_aliases.get(name)
        if after_def is None:
            violations.append(f"type alias {name!r} was removed")
        elif after_def != before_def:
            violations.append(f"type alias {name!r} changed from {before_def!r} to {after_def!r}")

    for name, before_import in before.imports.items():
        after_import = after.imports.get(name)
        if after_import is None:
            violations.append(
                f"import {name!r} (from {before_import.module}) is no longer a top-level "
                f"import -- moved inside a conditional/try block, renamed, or removed entirely"
            )
        elif after_import != before_import:
            violations.append(
                f"import {name!r} changed from module {before_import.module!r} "
                f"to module {after_import.module!r}"
            )

    return violations
