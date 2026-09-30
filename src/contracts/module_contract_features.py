"""Synthesizes an `IterativeTDDRunner`-ready `FeatureSpec` directly from a
`module_contract_schema.ContractDocument`, for a schema-driven module that
has no hand-written `.feature` file.

From `IterativeTDDRunner`'s point of view this is completely equivalent to
a real `GherkinFeatureBridge.parse()` result -- same `FeatureSpec`/
`ScenarioSpec` types, same one-scenario-per-RED/GREEN/REFACTOR-cycle
behavior. See `src/cli/project_builder.py::ProjectBuilder._build_module_iterative`
for how this is used: a real `.feature` file, when one exists, always wins;
this only fills the gap for the common case of a schema-driven module with
no hand-written one.

The contract schema's prose fields (`semantics`/`algorithm`/
`preconditions`/`raises`) are already written with the same level of
behavioral detail a hand-written Gherkin scenario has -- this is mostly
mechanical reformatting of prose that already exists, not inventing new
understanding of the module.

Structural-only entries (`constant`, `type_alias`, `protocol`, `abc`) get no
scenario at all: the deterministic scaffold + `ProtectedShape` lock already
guarantee their shape with no LLM involvement and no GREEN cycle needed. A
`protocol`/`abc` entry also has no concrete instance of its own to exercise
-- its conforming implementation, if any, lives in a `concrete_class` entry
elsewhere in the same contract (which does get scenarios) or is out of
scope for this module entirely.
"""
from __future__ import annotations

from src.agents.gherkin_feature_bridge import FeatureSpec, ScenarioSpec
from src.contracts.module_contract_scaffold import fixture_factory_name
from src.contracts.module_contract_schema import ApiEntry, ContractDocument, RaisesSpec

_NO_SCENARIO_KINDS = frozenset({"constant", "type_alias", "protocol", "abc"})


def _raises_steps(raises: list[RaisesSpec]) -> list[str]:
    """One concrete, assertion-shaped step per raised exception -- names the
    exception type and the condition, never a vague "handles errors"."""
    steps = []
    for r in raises:
        when = f" when {r.when}" if r.when else ""
        steps.append(f"Then a {r.exception} is raised{when}")
    return steps


def _callable_steps(
    name: str,
    *,
    returns: str = "",
    preconditions: list[str] | None = None,
    raises: list[RaisesSpec] | None = None,
    semantics: str = "",
) -> list[str]:
    """Concrete, assertion-shaped step lines that explicitly name `name`
    and state its expected return type or raised exception -- e.g. "Then
    run_online_rollout returns a DiscoveryTree", never a vague placeholder
    like "Then it behaves correctly". This is what actually gives RED
    enough to write a targeted, assertion-rich test instead of a shallow
    smoke test."""
    steps: list[str] = []
    if semantics:
        steps.append(f"Given {name}: {semantics}")
    for pre in preconditions or []:
        steps.append(f"Given {pre}")
    if returns:
        steps.append(f"Then {name} returns {returns}")
    steps.extend(_raises_steps(raises or []))
    if not steps:
        # No returns/preconditions/raises/semantics at all is rare (the
        # schema doesn't require any of them), but must still produce a
        # named, non-empty scenario rather than silently dropping it.
        steps.append(f"Then {name} behaves per its contract")
    return steps


def _constructor_step(entry: ApiEntry) -> str:
    """Describes how to build one instance of `entry` -- via its scaffolded
    `make_valid_<name>(**overrides)` fixture factory when one exists (every
    dataclass/pydantic-model entry with fields, once `module_contract_scaffold`
    has run), so RED writes tests against the factory instead of
    constructing a many-field object inline; otherwise from its
    `constructor.params` (concrete_class/abc) or, when there is no
    constructor, its `fields` (frozen/mutable dataclass -- these are
    constructed by field, not a separate constructor spec)."""
    factory = fixture_factory_name(entry)
    if factory:
        return f"Given a {entry.name} built via {factory}(**overrides)"
    if entry.constructor and entry.constructor.params:
        params = ", ".join(f"{p.name}: {p.type}" for p in entry.constructor.params)
        return f"Given a {entry.name} constructed with {params}"
    if entry.fields:
        fields = ", ".join(f"{f.name}: {f.type}" for f in entry.fields)
        return f"Given a {entry.name} constructed with {fields}"
    return f"Given a {entry.name} constructed with no arguments"


def _method_scenarios(entry: ApiEntry) -> list[ScenarioSpec]:
    """One scenario per method in `entry.methods` -- shared by dataclass and
    concrete_class entries, since a dataclass kind can carry its own real
    methods too (e.g. discovery_tree's `DiscoveryTree.attach`/`.children_of`,
    `Node.is_root`) that need exactly the same behavioral coverage a
    concrete_class's methods get. These are exactly the kind of methods a
    dependent module can otherwise hallucinate as free functions (see #73)
    -- covering them here is deliberate."""
    scenarios = []
    for m in entry.methods:
        name = f"{entry.name}.{m.name}"
        steps = [_constructor_step(entry)]
        steps.extend(
            _callable_steps(
                name, returns=m.returns, preconditions=m.preconditions,
                raises=m.raises, semantics=m.semantics,
            )
        )
        scenarios.append(ScenarioSpec(name=name, steps=steps))
    return scenarios


def _scenarios_for_dataclass(entry: ApiEntry) -> list[ScenarioSpec]:
    """Plain construction alone needs no scenario -- the scaffold already
    guarantees the fields/frozen-ness exist. Its own methods (if any) and a
    per-entry `raises` (a real runtime invariant, e.g. discovery_tree.Node's
    "parent_id is None => score is None") are what's worth a behavioral
    test."""
    scenarios = _method_scenarios(entry)
    if entry.raises:
        steps = [_constructor_step(entry), *_raises_steps(entry.raises)]
        scenarios.append(ScenarioSpec(name=f"{entry.name} enforces its invariants", steps=steps))
    return scenarios


def _scenarios_for_concrete_class(entry: ApiEntry) -> list[ScenarioSpec]:
    if not entry.methods:
        # Constructor-only concrete class (no methods to iterate) still
        # needs its own scenario -- never skipped just because entry.methods
        # is empty.
        return [
            ScenarioSpec(
                name=f"{entry.name} construction",
                steps=[_constructor_step(entry), f"Then a {entry.name} instance is created"],
            )
        ]
    return _method_scenarios(entry)


def _scenarios_for_function(entry: ApiEntry) -> list[ScenarioSpec]:
    steps = _callable_steps(
        entry.name, returns=entry.returns, preconditions=entry.preconditions,
        raises=entry.raises, semantics=entry.semantics,
    )
    return [ScenarioSpec(name=entry.name, steps=steps)]


_BUILDERS = {
    "frozen_dataclass": _scenarios_for_dataclass,
    "mutable_dataclass": _scenarios_for_dataclass,
    "concrete_class": _scenarios_for_concrete_class,
    "function": _scenarios_for_function,
}


def synthesize_feature_from_contract(doc: ContractDocument) -> tuple[FeatureSpec, str]:
    """Returns `(feature, context)` -- `feature` is an `IterativeTDDRunner`-
    ready `FeatureSpec`; `context` is a rendered plain-text description of
    the contract (module + description + each included entry's own prose),
    the synthesized analogue of a real `.feature` file's raw text, handed to
    RED the same way `_build_module_iterative` hands it real feature text.

    A contract whose every entry is structural-only (all constants/aliases/
    protocols/ABCs -- no scenario-worthy entry at all) still returns one
    fallback scenario asserting the module imports cleanly:
    `IterativeTDDRunner` needs at least one scenario to run at all.
    """
    scenarios: list[ScenarioSpec] = []
    context_parts = [f"Module: {doc.module}", doc.description]

    for entry in doc.public_api:
        if entry.kind in _NO_SCENARIO_KINDS:
            continue
        builder = _BUILDERS.get(entry.kind)
        if builder is None:
            continue
        entry_scenarios = builder(entry)
        if not entry_scenarios:
            continue
        scenarios.extend(entry_scenarios)
        context_parts.append(f"{entry.name}: {entry.description or entry.semantics}")

    if not scenarios:
        scenarios.append(
            ScenarioSpec(
                name=f"{doc.module} imports cleanly",
                steps=[f"Then the {doc.module} module imports without error"],
            )
        )

    factory_names = [n for n in (fixture_factory_name(e) for e in doc.public_api) if n]
    if factory_names:
        context_parts.append(
            "Test fixture factories available: "
            + ", ".join(f"{name}(**overrides)" for name in factory_names)
            + " -- prefer these over constructing instances field-by-field."
        )

    feature = FeatureSpec(title=doc.description or doc.module, scenarios=scenarios)
    context = "\n".join(p for p in context_parts if p)
    return feature, context
