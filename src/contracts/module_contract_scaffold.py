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
"""
from __future__ import annotations

from src.contracts.module_contract_schema import (
    ApiEntry,
    ConstructorSpec,
    ContractDocument,
    MethodSpec,
)

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
    return "".join(out)
