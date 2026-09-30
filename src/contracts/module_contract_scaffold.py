"""Corners-first deterministic scaffolding: compiles a validated
`module_contract_schema.ContractDocument` into Python source for every
`public_api` entry -- frozen/mutable dataclasses or pydantic models,
`typing.Protocol` definitions (including property-shaped members), ABCs,
type aliases, constants, top-level function stubs, and concrete-class stubs
with `NotImplementedError` method bodies -- so `ace project --from-spec-dir`
can pre-seed a module's implementation file before its first
`IterativeTDDRunner` cycle, leaving only method bodies for the LLM to fill
in against an already-fixed shape.

Ported from dream_rsi's `scripts/contract_scaffold.py` v2 (prototyped and
proven there first, dream_rsi commit `27aefee`), refactored as a library:
`scaffold_module()` takes a parsed `ContractDocument` directly (no file I/O)
and an optional `dependency_exports` map so a dependency's real, already-
built types can be imported instead of left undefined -- see
`ProjectBuilder._try_scaffold_module` for how both are resolved from a
`ProjectPlan`.

Every entry in every valid contract scaffolds; there is no string/regex
parsing of contract content in this file at all -- everything comes off the
already-validated `ContractDocument`/`ApiEntry` schema directly.

Also emits one `make_valid_<name>(**overrides)` fixture-factory function per
dataclass/pydantic-model entry (see `fixture_factory_name`/
`_emit_fixture_factory`) -- a test never has to construct a many-field
contract object inline, which is both the actual friction a real experiment
found the Reflector misdiagnosing as "the schema needs defaults" (it
doesn't; the fixture was just missing) and, being a real top-level `def`
from the moment it's scaffolded, automatically locked by the same
`ProtectedShape` walk as everything else here.
"""
from __future__ import annotations

import re

from src.contracts.module_contract_schema import (
    ApiEntry,
    ConstructorSpec,
    ContractDocument,
    MethodSpec,
)

_DATACLASS_KINDS = frozenset({"frozen_dataclass", "mutable_dataclass"})

_HEADER_TEMPLATE = '''# AUTO-GENERATED CORNERS from the "{module}" contract -- fill in method
# bodies, do not change the type/Protocol/dataclass/ABC shapes above this
# point.
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

try:
    from pydantic import BaseModel, ConfigDict
except ImportError:  # pragma: no cover - only needed for pydantic_model entries
    BaseModel = object  # type: ignore[assignment,misc]
    ConfigDict = dict  # type: ignore[assignment]

{imports}

'''


def _method_stub_lines(methods: list[MethodSpec], module: str, owner: str) -> list[str]:
    lines: list[str] = []
    for m in methods:
        lines.append("")
        if m.property:
            lines.append("    @property")
            lines.append(f"    def {m.name}(self) -> None:  # {m.signature}")
        else:
            lines.append(f"    def {m.signature}:")
        lines.append(
            f'        raise NotImplementedError("TODO: implement {m.name} per '
            f'the {module!r} contract\'s algorithm/semantics for {owner}.{m.name}")'
        )
    return lines


def _emit_dataclass(entry: ApiEntry, module: str) -> str:
    frozen = entry.kind == "frozen_dataclass"
    lines: list[str]
    if entry.impl == "pydantic_model":
        lines = [f"class {entry.name}(BaseModel):"]
        if frozen:
            lines.append("    model_config = ConfigDict(frozen=True)")
        if not entry.fields:
            lines.append("    pass")
        for f in entry.fields:
            if f.default is not None:
                lines.append(f"    {f.name}: {f.type} = {f.default}")
            else:
                lines.append(f"    {f.name}: {f.type}")
    else:
        lines = [f"@dataclass(frozen={frozen})", f"class {entry.name}:"]
        if not entry.fields:
            lines.append("    pass")
        for f in entry.fields:
            if f.default is not None:
                lines.append(f"    {f.name}: {f.type} = {f.default}")
            else:
                lines.append(f"    {f.name}: {f.type}")
    lines.extend(_method_stub_lines(entry.methods, module, entry.name))
    return "\n".join(lines) + "\n\n\n"


def _emit_protocol(entry: ApiEntry, module: str) -> str:
    lines = []
    if entry.runtime_checkable:
        lines.append("@runtime_checkable")
    lines.append(f"class {entry.name}(Protocol):")
    body_start = len(lines)
    for m in entry.methods:
        if m.property:
            lines.append("    @property")
            lines.append(f"    def {m.name}(self) -> None:  # {m.signature}")
            lines.append("        ...")
        else:
            lines.append(f"    def {m.signature}: ...")
    if len(lines) == body_start:
        lines.append("    ...")
    return "\n".join(lines) + "\n\n\n"


def _init_lines(constructor: ConstructorSpec | None) -> list[str]:
    params = constructor.params if constructor else []
    init_params = ["self"]
    for p in params:
        init_params.append(f"{p.name}: {p.type}" + (f" = {p.default}" if p.default is not None else ""))
    lines = [f"    def __init__({', '.join(init_params)}) -> None:"]
    if params:
        for p in params:
            lines.append(f"        self._{p.name} = {p.name}")
    else:
        lines.append("        pass")
    return lines


def _emit_abc(entry: ApiEntry, module: str) -> str:
    lines = [f"class {entry.name}(ABC):"]
    lines.extend(_init_lines(entry.constructor))
    for m in entry.methods:
        lines.append("")
        lines.append("    @abstractmethod")
        lines.append(f"    def {m.signature}:")
        lines.append(
            f'        raise NotImplementedError("TODO: implement {m.name} per '
            f'the {module!r} contract\'s algorithm/semantics for {entry.name}.{m.name}")'
        )
    return "\n".join(lines) + "\n\n\n"


def _emit_concrete_class(entry: ApiEntry, module: str) -> str:
    lines = [f"class {entry.name}:"]
    lines.extend(_init_lines(entry.constructor))
    lines.extend(_method_stub_lines(entry.methods, module, entry.name))
    return "\n".join(lines) + "\n\n\n"


def _emit_type_alias(entry: ApiEntry, module: str) -> str:
    return f"{entry.name} = {entry.definition}\n\n\n"


def _emit_function(entry: ApiEntry, module: str) -> str:
    signature = entry.signature or "()"
    return (
        f"def {entry.name}{signature}:\n"
        f'    raise NotImplementedError("TODO: implement {entry.name} per '
        f'the {module!r} contract\'s algorithm/semantics")\n\n\n'
    )


def _emit_constant(entry: ApiEntry, module: str) -> str:
    annotation = entry.type or "Any"
    if annotation in ("int", "float", "bool") and entry.value is not None:
        return f"{entry.name}: {annotation} = {entry.value}\n\n\n"
    value = "" if entry.value is None else str(entry.value).strip()
    return f"{entry.name}: {annotation} = {value!r}\n\n\n"


_EMITTERS = {
    "frozen_dataclass": _emit_dataclass,
    "mutable_dataclass": _emit_dataclass,
    "protocol": _emit_protocol,
    "abc": _emit_abc,
    "concrete_class": _emit_concrete_class,
    "type_alias": _emit_type_alias,
    "function": _emit_function,
    "constant": _emit_constant,
}


def _snake_case(name: str) -> str:
    """PascalCase/CamelCase -> snake_case, e.g. 'WorkspaceSnapshot' ->
    'workspace_snapshot'. Entry names are always valid Python identifiers
    already (contract-validated), so no further sanitization is needed."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def fixture_factory_name(entry: ApiEntry) -> str | None:
    """'make_valid_<snake_case(entry.name)>' for a dataclass/pydantic-model
    entry with at least one field; None otherwise (nothing to construct, or
    not a kind this scaffolder builds a fixture for)."""
    if entry.kind not in _DATACLASS_KINDS or not entry.fields:
        return None
    return f"make_valid_{_snake_case(entry.name)}"


def _is_optional_type(type_str: str) -> bool:
    """True for a top-level `X | None` (or `None | X`) union -- checked
    before anything else in `_default_value_expr` so a recursive-but-
    optional field (e.g. `parent: Node | None`) always resolves to `None`
    safely, regardless of whether `Node` participates in a reference cycle."""
    parts = [p.strip() for p in type_str.split("|")]
    return len(parts) > 1 and "None" in parts


def _literal_first_value(type_str: str) -> str | None:
    """First element of a `Literal[...]` type string, taken verbatim (already
    a valid Python literal), or None if `type_str` isn't a Literal."""
    t = type_str.strip()
    if not t.startswith("Literal[") or not t.endswith("]"):
        return None
    inner = t[len("Literal[") : -1]
    first = inner.split(",")[0].strip()
    return first or None


_PRIMITIVE_DEFAULTS = {"str": "''", "int": "0", "float": "0.0", "bool": "False"}


def _primitive_default(type_str: str) -> str | None:
    t = type_str.strip()
    if t in _PRIMITIVE_DEFAULTS:
        return _PRIMITIVE_DEFAULTS[t]
    if t.startswith("dict"):
        return "{}"
    if t.startswith("list"):
        return "[]"
    return None


def _cyclic_dataclass_entries(doc: ContractDocument) -> set[str]:
    """Names of dataclass/pydantic-model entries that sit on a reference
    cycle through a required (non-Optional, no-default) field -- a direct
    self-reference (`current: Node`) counts as a 1-node cycle. A cyclic
    entry's own factory must never be called recursively from within
    another (or its own) factory, since every dataclass entry gets a
    factory unconditionally -- doing so would emit an infinite call chain
    (`make_valid_node()` calling `make_valid_node()` calling ...)."""
    entries_by_name = {e.name: e for e in doc.public_api if e.kind in _DATACLASS_KINDS}
    graph: dict[str, set[str]] = {name: set() for name in entries_by_name}
    for name, entry in entries_by_name.items():
        for f in entry.fields:
            if f.default is not None or _is_optional_type(f.type):
                continue
            target = f.type.strip()
            if target in entries_by_name:
                graph[name].add(target)

    cyclic: set[str] = set()
    UNVISITED, VISITING, DONE = 0, 1, 2
    state = dict.fromkeys(entries_by_name, UNVISITED)

    def visit(node: str, stack: list[str]) -> None:
        state[node] = VISITING
        stack.append(node)
        for neighbor in graph[node]:
            if state[neighbor] == VISITING:
                cyclic.update(stack[stack.index(neighbor) :])
            elif state[neighbor] == UNVISITED:
                visit(neighbor, stack)
        stack.pop()
        state[node] = DONE

    for name in entries_by_name:
        if state[name] == UNVISITED:
            visit(name, [])
    return cyclic


def _default_value_expr(field_type: str, factory_names: dict[str, str], cyclic_entries: set[str]) -> tuple[str, str | None]:
    """Best-effort `(expr, note)` for a field with no contract-declared
    default, checked in this order so the riskier heuristics never get a
    chance to misfire on a case an earlier, safer check already handles.
    `note`, when not None, is a human-readable reason to surface as a
    trailing comment -- never merged into `expr` itself, since a `#`
    embedded before the line's own trailing comma would swallow it and
    break the enclosing `dict(...)` call's argument list."""
    if _is_optional_type(field_type):
        return "None", None
    literal_value = _literal_first_value(field_type)
    if literal_value is not None:
        return literal_value, None
    primitive = _primitive_default(field_type)
    if primitive is not None:
        return primitive, None
    name = field_type.strip()
    if name in factory_names and name not in cyclic_entries:
        return f"{factory_names[name]}()", None
    return "None", f"override required: {field_type}"


def _emit_fixture_factory(entry: ApiEntry, factory_names: dict[str, str], cyclic_entries: set[str]) -> str:
    name = factory_names[entry.name]
    lines = [
        f"def {name}(**overrides) -> {entry.name}:",
        f'    """Test fixture -- constructs a valid {entry.name} with sensible',
        '    defaults for every required field, overridable via keyword arguments."""',
        "    defaults = dict(",
    ]
    for f in entry.fields:
        if f.default is not None:
            value, note = f.default, None
        else:
            value, note = _default_value_expr(f.type, factory_names, cyclic_entries)
        line = f"        {f.name}={value},"
        if note:
            line += f"  # {note}"
        lines.append(line)
    lines.append("    )")
    lines.append("    defaults.update(overrides)")
    lines.append(f"    return {entry.name}(**defaults)")
    return "\n".join(lines) + "\n\n\n"


def _import_lines(dependency_exports: dict[str, list[str]] | None) -> str:
    """One `from <dep> import <name1>, <name2>, ...` line per dependency,
    sorted by dependency name (and by export name within each line) for
    deterministic output. A dependency with no exports is skipped rather
    than emitting an empty import."""
    if not dependency_exports:
        return ""
    lines = [
        f"from {dep} import {', '.join(sorted(names))}"
        for dep, names in sorted(dependency_exports.items())
        if names
    ]
    return "\n".join(lines)


def scaffold_module(
    doc: ContractDocument,
    dependency_exports: dict[str, list[str]] | None = None,
) -> str:
    """Compile `doc` into Python source. `dependency_exports` maps each
    dependency module name (from `doc.depends_on`) to the list of names its
    own contract's `public_api` declares -- used to emit
    `from <dep> import <Name1>, <Name2>, ...` so those types resolve for
    real once the dependency is actually built alongside this module,
    instead of being left as undefined names in a lazily-evaluated
    annotation."""
    header = _HEADER_TEMPLATE.format(module=doc.module, imports=_import_lines(dependency_exports))
    out = [header]
    for entry in doc.public_api:
        emitter = _EMITTERS[entry.kind]
        out.append(emitter(entry, doc.module))

    factory_names: dict[str, str] = {}
    for entry in doc.public_api:
        fname = fixture_factory_name(entry)
        if fname is not None:
            factory_names[entry.name] = fname
    if factory_names:
        cyclic_entries = _cyclic_dataclass_entries(doc)
        for entry in doc.public_api:
            if entry.name in factory_names:
                out.append(_emit_fixture_factory(entry, factory_names, cyclic_entries))

    return "".join(out)
