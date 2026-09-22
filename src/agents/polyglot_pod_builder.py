"""
build_pod_kwargs — per-language construction args for PodFactory.create().

Wires each language to its rootless-Podman-sandboxed runner (PodmanRunner /
TypeScriptRunner / GoRunner) so PodFactory always produces a pod that executes
generated code inside the container, never on the host. Intended for callers
like PolyglotTDDRunner(pod_factory, pod_kwargs=build_all_pod_kwargs(...)).
"""
from pathlib import Path
from typing import Any

_SUPPORTED_LANGUAGES = ("python", "typescript", "go")


def build_pod_kwargs(
    language: str,
    project_root: Path,
    llm_client: Any,
    src_dir: Path | None = None,
    playbook_manager=None,
    retrieval_service=None,
    team_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Return PodFactory.create() kwargs for one language, sandbox wired in.

    src_dir (defaults to project_root) is AST-scanned into a ContextMap for
    the Python worker's GREEN-phase prompts -- same context-injection used by
    ace tdd's build_agent(). TypeScript/Go workers don't accept context_map
    (TypeScriptWorkerAgent has no such param; Go has no separate worker).

    playbook_manager/retrieval_service/team_id/project_id are all optional
    and None by default -- callers that don't pass them get exactly today's
    behavior. retrieval_service should already be a constructed
    src.retrieval.service.InstitutionalKnowledgeService (or None); this
    function never builds one itself, since it's called once per language
    and the service (and the playbook_manager backing it) should be shared
    across all of a single build's languages, not re-created per call
    (ace_enterprise#67).
    """
    from src.agents.podman_orchestrator import PodmanOrchestrator

    src_dir = src_dir or project_root

    if language == "python":
        from src.agents.podman_runner import PodmanRunner
        from src.agents.worker_agent import WorkerAgent
        from src.utils.context_map import ContextMapBuilder
        context_map = ContextMapBuilder().build(sorted(src_dir.rglob("*.py")))
        return {
            "worker": WorkerAgent(
                llm_client, context_map=context_map, playbook_manager=playbook_manager,
                retrieval_service=retrieval_service, team_id=team_id, project_id=project_id,
                project_path=str(project_root),
            ),
            "project_root": project_root,
            "orchestrator": PodmanOrchestrator(runner=PodmanRunner()),
        }
    if language == "typescript":
        from src.agents.typescript_runner import TypeScriptRunner
        from src.agents.typescript_worker_agent import TypeScriptWorkerAgent
        return {
            "worker": TypeScriptWorkerAgent(
                llm_client, playbook_manager=playbook_manager, retrieval_service=retrieval_service,
                team_id=team_id, project_id=project_id, project_path=str(project_root),
            ),
            "project_root": project_root,
            "orchestrator": PodmanOrchestrator(runner=TypeScriptRunner()),
        }
    if language == "go":
        from src.agents.go_runner import GoRunner
        return {
            "llm_client": llm_client,
            "project_root": project_root,
            "orchestrator": PodmanOrchestrator(runner=GoRunner()),
            "playbook_manager": playbook_manager,
            "retrieval_service": retrieval_service,
            "team_id": team_id,
            "project_id": project_id,
        }
    raise ValueError(f"Unsupported language: {language!r} (expected one of {_SUPPORTED_LANGUAGES})")


def build_all_pod_kwargs(
    languages: list[str],
    project_root: Path,
    llm_client: Any,
    src_dir: Path | None = None,
    playbook_manager=None,
    retrieval_service=None,
    team_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    """build_pod_kwargs() for each requested language, keyed by language."""
    return {
        lang: build_pod_kwargs(
            lang, project_root, llm_client, src_dir,
            playbook_manager=playbook_manager, retrieval_service=retrieval_service,
            team_id=team_id, project_id=project_id,
        )
        for lang in languages
    }
