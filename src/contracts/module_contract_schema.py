"""Formal schema for module-level `.contract.yml` files.

Describes whole-module shape -- classes, dataclasses, Protocols, ABCs, type
aliases, functions, constants -- as opposed to this package's own
`contract_schema.py::ContractSpec`, a per-function, example-test-case schema
for a completely different purpose (one function's signature + literal
input/expected test cases). Different file, different classes, no overlap
to reconcile -- only a name collision at the concept level ("contract"),
never at the code level.

Ported from dream_rsi's `specs/contract_schema.py`, where it was prototyped
and stress-tested against 13 real, messy `.contract.yml` files before this
port (dream_rsi commit `27aefee`). Consumed by `module_contract_scaffold.py`
to pre-seed a module's type-level "corners" (frozen dataclasses, Protocols,
ABCs, type aliases, constants, concrete-class stubs) before `ace project
--from-spec-dir` hands a module to `IterativeTDDRunner`, so the LLM only
ever has to fill in method bodies against an already-fixed shape.

Design principle: only the STRUCTURAL, type-bearing parts of a contract
(entry-type tags, `kind:`, `fields:` values, `constructor:` params,
`methods:` shapes) get a real schema here. The PROSE parts (`semantics:`,
`algorithm:`, `description:`, `paper_ref:`, module-level `invariants:`)
stay free text -- nothing tries to mechanically parse them, so tightening
them into a rigid schema would only strip nuance for no benefit.
"""
from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

EntryKind = Literal[
    "frozen_dataclass",
    "mutable_dataclass",
    "protocol",
    "abc",
    "concrete_class",
    "type_alias",
    "function",
    "constant",
]

_DATACLASS_KINDS = frozenset({"frozen_dataclass", "mutable_dataclass"})


class RaisesSpec(BaseModel):
    exception: str
    when: str = ""


class FieldSpec(BaseModel):
    """One dataclass/model field. `type`/`default`/`comment` are always
    separate keys -- never a single ambiguous string that needs re-parsing
    to recover which part is which."""

    name: str
    type: str
    default: str | None = None
    comment: str | None = None


class ParamSpec(BaseModel):
    """One constructor parameter. `type` is always its own key, so a
    nested-comma type like `Callable[[str, str], bool]` never needs
    bracket-depth-aware splitting out of a larger signature string."""

    name: str
    type: str
    default: str | None = None


class ConstructorSpec(BaseModel):
    params: list[ParamSpec] = Field(default_factory=list)


class MethodSpec(BaseModel):
    """One method (or, if `property` is true, one property) on a
    `protocol`/`abc`/`concrete_class` entry. Always the same shape
    regardless of the parent entry's kind -- the parent's own `kind:`
    already says what decorator/base applies, so the list itself never
    needs its own name to repeat that."""

    name: str
    signature: str
    property: bool = False
    semantics: str = ""
    algorithm: str = ""
    returns: str = ""
    preconditions: list[str] = Field(default_factory=list)
    raises: list[RaisesSpec] = Field(default_factory=list)


class ApiEntry(BaseModel):
    """One `public_api` entry. `name`+`kind` (a closed enum) give every
    entry a uniform shape regardless of what it represents."""

    name: str
    kind: EntryKind
    description: str = ""
    semantics: str = ""
    algorithm: str = ""
    notes: str = ""
    constructor_notes: str = ""
    formula: str = ""
    returns: str = ""
    preconditions: list[str] = Field(default_factory=list)
    raises: list[RaisesSpec] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)

    # frozen_dataclass / mutable_dataclass
    fields: list[FieldSpec] = Field(default_factory=list)
    impl: Literal["dataclass", "pydantic_model"] = "dataclass"

    # protocol / abc / concrete_class
    methods: list[MethodSpec] = Field(default_factory=list)
    constructor: ConstructorSpec | None = None
    runtime_checkable: bool = True  # only meaningful when kind == "protocol"

    # type_alias
    definition: str | None = None

    # function
    signature: str | None = None

    # constant
    type: str | None = None
    value: str | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> ApiEntry:
        if self.kind == "type_alias" and not self.definition:
            raise ValueError(f"{self.name}: kind=type_alias requires 'definition'")
        if self.kind == "function":
            if not self.signature:
                raise ValueError(f"{self.name}: kind=function requires 'signature'")
            if not self.signature.lstrip().startswith("("):
                # A top-level function's signature is always bare "(args) ->
                # ret", never repeating `name` (which already has its own
                # key) -- unlike a MethodSpec's signature, which legitimately
                # includes its own name+self.
                raise ValueError(
                    f"{self.name}: kind=function signature must be bare "
                    f"'(args) -> ret', not repeat the function's own name "
                    f"(got {self.signature!r})"
                )
        if self.kind == "constant" and self.value is None:
            raise ValueError(f"{self.name}: kind=constant requires 'value'")
        if self.kind == "concrete_class" and self.constructor is None:
            raise ValueError(f"{self.name}: kind=concrete_class requires 'constructor'")

        if self.kind in _DATACLASS_KINDS and self.impl == "dataclass":
            # A real Python constraint, checked here so a migration mistake
            # is caught at validation time, not as a SyntaxError from the
            # scaffolder: every field without a default must precede every
            # field that has one. Pydantic models (impl == "pydantic_model")
            # don't go through the stdlib dataclasses machinery and have no
            # such ordering restriction, so this only applies to real
            # dataclasses.
            seen_default = False
            for f in self.fields:
                if f.default is not None:
                    seen_default = True
                elif seen_default:
                    raise ValueError(
                        f"{self.name}.{f.name}: field with no default follows "
                        f"a field that has one -- invalid dataclass field order"
                    )
        return self


class ContractDocument(BaseModel):
    """Top-level `.contract.yml` shape: `module`/`version`/`paper_ref`/
    `depends_on`/`external_dependencies`/`description`/`public_api`/
    `invariants`/`notes`."""

    module: str
    version: str = "0.1.0"
    paper_ref: str = ""
    depends_on: list[str] = Field(default_factory=list)
    external_dependencies: list[str] = Field(default_factory=list)
    description: str = ""
    public_api: list[ApiEntry] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_yaml(cls, text: str) -> ContractDocument:
        return cls.model_validate(yaml.safe_load(text))
