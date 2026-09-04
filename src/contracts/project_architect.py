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

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
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
    `ModuleArchitect`."""

    name: str
    description: str
    depends_on: tuple[str, ...] = ()


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
    def ordered_modules(self) -> list[ModuleSpec]:
        by_name = {m.name: m for m in self.modules}
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
