"""Build a sandboxed IterativeTDDRunner wired to a target project.

Mirrors bootstrap/orchestrate.py's synthesis loop: RED/GREEN/REFACTOR execute
inside a rootless Podman container via PythonLanguagePod. Generated code is
committed to config.src_dir / config.test_dir only after it passes inside the
sandbox (pod.commit_to_disk() is gated on the in-container pulse result) --
`ace tdd` never writes or runs LLM-generated code directly on the host.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.agents.gherkin_feature_bridge import GherkinFeatureBridge
from src.agents.iterative_tdd_runner import IterativeResult, IterativeTDDRunner
from src.agents.podman_orchestrator import PodmanOrchestrator
from src.broker.model_router import ModelRoutingDecision, route_model
from src.cli.config import ProjectConfig
from src.config.settings import settings
from src.utils.llm_client import LLMClient


@dataclass
class TDDRunHandle:
    """Owns the sandbox container lifecycle for one `ace tdd` invocation."""

    runner: IterativeTDDRunner
    orchestrator: PodmanOrchestrator
    test_dir: Path
    src_dir: Path
    # Set when config.candidate_models had 2+ entries and the AdaptiveBroker
    # picked which one runs this build; None when a single fixed model is used.
    routing: ModelRoutingDecision | None = None

    def build_from_feature(self, feature_path: Path, requirement: str | None = None) -> IterativeResult:
        """Run the Gherkin-driven TDD loop for one .feature file.

        Mirrors IterativeTDDRunner.run_from_feature(), except an explicit
        `requirement` (e.g. from --requirement) overrides the one derived
        from the feature file instead of being silently ignored.
        """
        feature_path = Path(feature_path)
        spec = GherkinFeatureBridge.parse(feature_path)
        stem = feature_path.stem
        return self.runner.run(
            requirement=requirement or spec.as_requirement(),
            gherkin_context=feature_path.read_text(encoding="utf-8"),
            gherkin_scenarios=spec.scenarios,
            test_file=self.test_dir / f"test_{stem}.py",
            impl_file=self.src_dir / f"{stem}.py",
        )

    def file_paths_for(self, feature_path: Path) -> tuple[Path, Path]:
        stem = Path(feature_path).stem
        return self.test_dir / f"test_{stem}.py", self.src_dir / f"{stem}.py"

    def stop(self) -> None:
        self.orchestrator.stop()


def build_agent(
    config: ProjectConfig,
    skip_learn: bool = False,
    model_ref: str | None = None,
) -> TDDRunHandle:
    """Construct a fully-wired, sandboxed TDDRunHandle for the given project config.

    Model selection, highest precedence first:
      1. model_ref  — an explicit "<provider>/<model>" (the `ace tdd --model` flag)
      2. config.candidate_models (2+)  — AdaptiveBroker routing
      3. ACE's settings default (.env)

    The playbook_id comes from config, scoping learned patterns to this project.
    skip_learn=True omits the Reflector/Curator LEARN phase (the old --no-learn).

    Also wires the audit trail, redundancy pre-check, and AST context map --
    capabilities AutonomousTDDAgent had natively that IterativeTDDRunner needs
    handed in explicitly (see tdd_cycle_runner.py's audit_client and
    iterative_tdd_runner.py's redundancy_checker params).
    """
    from src.agents.incremental_planner import IncrementalPlanner
    from src.agents.podman_runner import PodmanRunner
    from src.agents.python_language_pod import PythonLanguagePod
    from src.agents.redundancy_checker import RedundancyPreChecker
    from src.agents.worker_agent import WorkerAgent
    from src.audit.local_client import LocalAuditClient
    from src.core.curator.module import Curator
    from src.core.reflector.module import Reflector
    from src.playbook.manager import PlaybookManager
    from src.utils.context_map import ContextMapBuilder

    audit_client = LocalAuditClient()

    routing = None
    if model_ref:
        llm_client = llm_client_from_ref(model_ref)
    else:
        routing = _route_llm(config, audit_client)
        if routing is not None:
            llm_client = llm_client_from_ref(routing.selected_model)
        else:
            llm_client = default_llm_client()

    playbook_manager = PlaybookManager()
    playbook_manager.get_or_create_playbook(config.playbook_id)

    # Compact AST signatures of the project's existing source, so GREEN-phase
    # prompts reference relevant functions without pasting whole files.
    context_map = ContextMapBuilder().build(sorted(config.src_dir.rglob("*.py")))

    worker = WorkerAgent(llm_client, playbook_manager=playbook_manager, context_map=context_map)
    planner = IncrementalPlanner(
        llm_client=llm_client,
        test_dir=config.test_dir,
        src_dir=config.src_dir,
        playbook_manager=playbook_manager,
        playbook_id=config.playbook_id,
    )
    orchestrator = PodmanOrchestrator(runner=PodmanRunner())
    pod = PythonLanguagePod(worker, config.project_root, orchestrator)

    reflector = curator = None
    if not skip_learn:
        reflector = Reflector(llm_client=llm_client)
        curator = Curator(playbook_manager=playbook_manager, llm_client=llm_client)

    runner = IterativeTDDRunner(
        pod=pod,
        planner=planner,
        max_iterations=config.max_iterations,
        playbook_id=config.playbook_id,
        reflector=reflector,
        curator=curator,
        audit_client=audit_client,
        redundancy_checker=RedundancyPreChecker(),
        team_id=config.team_id,
        model_id=f"{llm_client.provider}/{llm_client.model}",
        task_type="python",
    )
    return TDDRunHandle(
        runner=runner,
        orchestrator=orchestrator,
        test_dir=config.test_dir,
        src_dir=config.src_dir,
        routing=routing,
    )


# Mirrors the Literal in src/config/settings.py::Settings.default_llm_provider.
_VALID_PROVIDERS = frozenset(
    {"ollama", "vllm", "deepseek", "togetherai", "openrouter", "openai", "anthropic"}
)


def _split_model_ref(ref: str) -> tuple[str, str]:
    """Split a "<provider>/<model>" ref. The model half may itself contain
    slashes (e.g. "openrouter/qwen/qwen3-coder:free")."""
    provider, sep, model = ref.partition("/")
    if not sep or not model:
        raise ValueError(
            f"model {ref!r} must be '<provider>/<model>' "
            "(e.g. 'openrouter/qwen/qwen3-coder', 'ollama/qwen3-coder:30b')"
        )
    if provider not in _VALID_PROVIDERS:
        raise ValueError(
            f"unknown provider {provider!r} in {ref!r} — expected one of: "
            + ", ".join(sorted(_VALID_PROVIDERS))
        )
    return provider, model


def llm_client_from_ref(ref: str) -> LLMClient:
    """Build an LLMClient from a "<provider>/<model>" ref."""
    provider, model = _split_model_ref(ref)
    return LLMClient(provider=provider, model=model)


def _route_llm(config: ProjectConfig, audit_client) -> ModelRoutingDecision | None:
    """Route this run to one of config.candidate_models via the AdaptiveBroker.

    Returns None (caller uses the ACE default model) unless 2+ candidates are
    configured. Emits a ROUTING_DECISION audit event so the choice is visible
    in the trail, consistent with the broker's "humans see everything" design.
    """
    if len(config.candidate_models) < 2:
        return None

    from src.audit.local_client import default_local_audit_url
    from src.audit.schemas import AuditEventType

    decision = route_model(
        config.candidate_models,
        task_type="python",
        audit_database_url=default_local_audit_url(),
    )
    try:
        audit_client.emit_simple(
            event_type=AuditEventType.ROUTING_DECISION,
            actor_id=decision.selected_model,
            payload=decision.to_payload(),
            playbook_id=config.playbook_id or None,
        )
    except Exception:  # noqa: BLE001 -- audit is best-effort, never blocks a build
        pass
    return decision


def default_llm_client() -> LLMClient:
    """The LLM client ACE uses when nothing more specific is chosen: provider
    from settings.default_llm_provider, model from that provider's default."""
    provider = settings.default_llm_provider
    return LLMClient(provider=provider, model=_default_model(provider))


def _default_model(provider: str) -> str:
    model_map = {
        "ollama": settings.ollama_default_model,
        "openrouter": settings.openrouter_default_model,
        "anthropic": settings.anthropic_default_model,
        "openai": settings.openai_default_model,
        "deepseek": settings.deepseek_default_model,
        "togetherai": settings.togetherai_default_model,
    }
    return model_map.get(provider, settings.ollama_default_model)
