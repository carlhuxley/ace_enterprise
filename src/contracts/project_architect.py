"""ProjectArchitect — decompose one project spec into a module DAG.

The layer above `ModuleArchitect`: given "build me an X", produce the list of
modules and the build-order dependencies between them. `ace project` prints
the plan for a human to approve, then `ProjectBuilder` builds each module
(via `ModuleArchitect` + `ModuleTDDBuilder`) in topological order.

One LLM call, one-shot: the whole module list is decided up front. Incremental
re-planning is a possible follow-up.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.contracts.module_contract_schema import ContractDocument
from src.utils.llm_client import LLMClient
from src.utils.topo import DependencyError, topo_order

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ProjectPlanError(ValueError):
    """The generated plan is malformed or can't be ordered."""


@dataclass(frozen=True)
class ModuleSpec:
    """One module in a project plan. `name` becomes `<name>.py` /
    `test_<name>.py`; `description` is the requirement handed to
    `ModuleArchitect`. `contract_yaml`, when set (only via
    `ProjectPlan.from_spec_dir`, issue #57 follow-up), is the raw text of
    this module's formal `.contract.yml` -- passed to `ModuleArchitect` as
    the authoritative interface instead of letting it re-derive the
    module's shape from `description` alone. `feature_path`, when set
    (also only via `from_spec_dir`, issue #59), routes this module through
    `IterativeTDDRunner` (one Gherkin scenario per RED/GREEN/REFACTOR
    cycle) instead of `ModuleTDDBuilder`'s one-shot batch contract
    synthesis -- see ProjectBuilder._build_module for the branch point."""

    name: str
    description: str
    depends_on: tuple[str, ...] = ()
    contract_yaml: str | None = None
    feature_path: Path | None = None
    # Set only when contract_yaml validates against the formal
    # module_contract_schema.ContractDocument (issue #70's scaffolding
    # support) -- most existing spec dirs use a plainer, schema-less
    # contract.yml and this stays None for them, which is not an error.
    # ProjectBuilder consults this (and each dependency's own
    # parsed_contract, via ProjectPlan.by_name) to decide whether to
    # pre-seed this module's implementation file with a deterministic
    # scaffold before its first IterativeTDDRunner cycle.
    parsed_contract: ContractDocument | None = None


@dataclass
class ProjectPlan:
    spec: str
    modules: list[ModuleSpec]
    build_order: list[str] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        names = [m.name for m in self.modules]
        if not names:
            raise ProjectPlanError("plan has no modules")
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ProjectPlanError(f"duplicate module name(s): {', '.join(dupes)}")
        for m in self.modules:
            if not _NAME_RE.match(m.name):
                raise ProjectPlanError(
                    f"module name {m.name!r} is not snake_case (^[a-z][a-z0-9_]*$)"
                )
        deps = {m.name: list(m.depends_on) for m in self.modules if m.depends_on}
        try:
            self.build_order = topo_order(sorted(names), deps)
        except DependencyError as exc:
            raise ProjectPlanError(str(exc)) from exc

    @property
    def by_name(self) -> dict[str, ModuleSpec]:
        return {m.name: m for m in self.modules}

    @property
    def ordered_modules(self) -> list[ModuleSpec]:
        by_name = self.by_name
        return [by_name[n] for n in self.build_order]

    @property
    def edges(self) -> list[tuple[str, str]]:
        return [(m.name, d) for m in self.modules for d in m.depends_on]

    def render(self) -> str:
        lines = [f"Project plan — {len(self.modules)} module(s), build order:"]
        for m in self.ordered_modules:
            dep = f"   ← {', '.join(m.depends_on)}" if m.depends_on else ""
            lines.append(f"  • {m.name} — {m.description}{dep}")
        return "\n".join(lines)

    def to_payload(self) -> dict:
        return {
            "decomposition_type": "project",
            "module_count": len(self.modules),
            "modules": [
                {"name": m.name, "description": m.description, "depends_on": list(m.depends_on)}
                for m in self.ordered_modules
            ],
            "build_order": list(self.build_order),
            "edges": [list(e) for e in self.edges],
        }

    @classmethod
    def from_spec_dir(cls, spec_dir: Path) -> ProjectPlan:
        """Build a plan directly from a structured spec directory --
        `contracts/<module>.contract.yml` per module, each stating its own
        `depends_on` -- bypassing ProjectArchitect's LLM decomposition
        entirely (issue #57). Each module's raw contract text is also
        carried on its `ModuleSpec.contract_yaml`, so `ProjectBuilder`
        passes the full formal interface -- exact class/method names,
        signatures, formulas, invariants -- to `ModuleArchitect` instead of
        the one-line `description` alone (issue #57 follow-up).

        Raises ProjectPlanError on any malformed input -- same exception
        type as the LLM path, so callers handle both identically.
        """
        contracts_dir = spec_dir / "contracts"
        if not contracts_dir.is_dir():
            contracts_dir = spec_dir
        contract_files = sorted(contracts_dir.glob("*.contract.yml"))
        if not contract_files:
            raise ProjectPlanError(f"no *.contract.yml files found under {spec_dir}")

        features_dir = spec_dir / "features"

        modules: list[ModuleSpec] = []
        for path in contract_files:
            raw_text = path.read_text(encoding="utf-8")
            try:
                data = yaml.safe_load(raw_text)
            except yaml.YAMLError as exc:
                raise ProjectPlanError(f"{path}: invalid YAML: {exc}") from exc
            if not isinstance(data, dict) or "module" not in data:
                raise ProjectPlanError(f"{path}: missing required top-level 'module' key")
            depends_on_raw = data.get("depends_on", []) or []
            if not isinstance(depends_on_raw, list):
                raise ProjectPlanError(f"{path}: 'depends_on' must be a list")
            module_name = str(data["module"]).strip()
            modules.append(
                ModuleSpec(
                    name=module_name,
                    description=str(data.get("description", "")).strip(),
                    depends_on=tuple(str(d).strip() for d in depends_on_raw if str(d).strip()),
                    feature_path=_iterative_feature_path(features_dir, module_name),
                    contract_yaml=raw_text,
                    parsed_contract=_try_parse_contract_document(path, raw_text),
                )
            )

        return cls(spec=f"structured spec dir: {spec_dir}", modules=modules)


def _try_parse_contract_document(path: Path, raw_text: str) -> ContractDocument | None:
    """None whenever raw_text doesn't validate against the formal module
    contract schema -- most existing spec dirs use a plainer, schema-less
    convention (just module/description/depends_on) and must keep planning
    exactly as before. This is a graceful degrade, never a ProjectPlanError:
    only from_spec_dir's own three required-key checks above are fatal."""
    try:
        return ContractDocument.from_yaml(raw_text)
    except Exception as exc:  # noqa: BLE001 -- any schema/YAML-shape mismatch degrades silently
        logger.debug("%s: does not validate against ContractDocument (%s) -- no scaffolding for this module", path, exc)
        return None


def _iterative_feature_path(features_dir: Path, module_name: str) -> Path | None:
    """Issue #59's routing signal: a companion `<module_name>.feature` file
    with 2+ scenarios means this module is algorithmic/stateful enough that
    it should be discovered incrementally (IterativeTDDRunner, one scenario
    per RED/GREEN/REFACTOR cycle) rather than committed to a full pre-
    rendered integration-test battery up front (ModuleTDDBuilder's batch
    path). A single-scenario or missing feature file, or one that fails to
    parse, returns None -- the batch path is the safe default, and a
    malformed feature file must not brick an otherwise-buildable module.
    """
    path = features_dir / f"{module_name}.feature"
    if not path.is_file():
        return None
    try:
        from src.agents.gherkin_feature_bridge import GherkinFeatureBridge

        spec = GherkinFeatureBridge.parse(path)
    except Exception as exc:  # noqa: BLE001 -- a bad feature file must not block planning
        logger.warning("%s: failed to parse as a Gherkin feature (%s) -- using batch build", path, exc)
        return None
    return path if len(spec.scenarios) >= 2 else None


@dataclass
class ProjectPlanResult:
    plan: ProjectPlan | None
    architect_model: str
    elapsed_seconds: float
    success: bool
    error: str | None = None


_SYSTEM_PROMPT = """You are a software architect. Break a project spec into the
smallest set of Python modules that each do one cohesive thing, and state the
build-order dependencies between them.

Rules:
- name: snake_case, becomes <name>.py
- description: one concrete sentence naming the functions/behaviour this module
  provides (a second model implements the module from this line alone)
- depends_on: names of modules this one imports from or calls into. If the
  module will use a function that belongs to another module, that other module
  MUST appear here. No cycles.
- 2-8 modules. Prefer a few cohesive modules over many tiny ones.

Output ONLY a JSON object, no prose:
{"modules": [{"name": "...", "description": "...", "depends_on": ["..."]}]}"""

_PROMPT = """Project spec:

{spec}

Break it into modules with build-order dependencies."""


class ProjectArchitect:
    """Decomposes a project spec into a `ProjectPlan`."""

    def __init__(
        self,
        llm_client: LLMClient,
        audit_client: LocalAuditClient | None = None,
        model_id: str = "unknown",
    ) -> None:
        self._llm = llm_client
        self._audit = audit_client
        self._model_id = model_id

    def plan(self, spec: str, session_id: str | None = None) -> ProjectPlanResult:
        start = time.time()
        try:
            raw_modules = self._generate_plan(spec)
            plan = self._parse_plan(spec, raw_modules)
        except ProjectPlanError as exc:
            return ProjectPlanResult(None, self._model_id, time.time() - start, False, str(exc))
        except Exception as exc:  # noqa: BLE001 -- surface any LLM/parse failure as a result
            logger.error("ProjectArchitect.plan failed: %s", exc)
            return ProjectPlanResult(None, self._model_id, time.time() - start, False, str(exc))

        self._emit(plan, session_id)
        return ProjectPlanResult(plan, self._model_id, time.time() - start, True)

    # -- seam for tests: patch this, not the LLM client --------------------

    def _generate_plan(self, spec: str) -> list[dict]:
        result = self._llm.generate(
            _PROMPT.format(spec=spec), system_prompt=_SYSTEM_PROMPT
        )
        return self._extract_modules(result["content"])

    # --------------------------------------------------------------------

    @staticmethod
    def _extract_modules(content: str) -> list[dict]:
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        text = fenced.group(1) if fenced else content
        obj = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
        if not obj:
            raise ProjectPlanError("no JSON found in architect response")
        try:
            data = json.loads(obj.group(0))
        except json.JSONDecodeError as exc:
            raise ProjectPlanError(f"architect response is not valid JSON: {exc}") from exc
        modules = data if isinstance(data, list) else data.get("modules")
        if not isinstance(modules, list) or not modules:
            raise ProjectPlanError("architect response has no non-empty 'modules' list")
        return modules

    def _parse_plan(self, spec: str, raw_modules: list[dict]) -> ProjectPlan:
        modules: list[ModuleSpec] = []
        for raw in raw_modules:
            if not isinstance(raw, dict) or "name" not in raw:
                raise ProjectPlanError(f"malformed module entry: {raw!r}")
            depends_on = tuple(
                str(d).strip() for d in raw.get("depends_on", []) or [] if str(d).strip()
            )
            modules.append(
                ModuleSpec(
                    name=str(raw["name"]).strip(),
                    description=str(raw.get("description", "")).strip(),
                    depends_on=depends_on,
                )
            )
        return ProjectPlan(spec=spec, modules=modules)

    def _emit(self, plan: ProjectPlan, session_id: str | None) -> None:
        if self._audit is None:
            return
        try:
            self._audit.emit_simple(
                event_type=AuditEventType.CONTRACT_DECOMPOSED,
                actor_id=self._model_id,
                payload=plan.to_payload(),
                session_id=session_id,
            )
        except Exception:  # noqa: BLE001 -- audit is best-effort
            logger.debug("project-decomposition audit emit failed", exc_info=True)
