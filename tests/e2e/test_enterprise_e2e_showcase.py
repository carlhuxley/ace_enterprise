"""Un-mocked, live end-to-end tests demonstrating ACE's core guarantees.

Requires:
  - podman in PATH, with ace-harness / ace-ts-harness / ace-go-harness
    images already built.
  - the `claude` CLI authenticated on this host (ClaudeCliClient -- no API
    key needed, uses the local Claude Code session).

Both are checked at collection time; tests skip (not fail) when either is
unavailable, matching the existing convention in tests/test_podman_runner.py.
These are slow (real containers, real subprocess LLM calls) by nature.

Architecture note (test 3): InstitutionalKnowledgeService/CGR3 and the pod's
own WorkerAgent playbook lookup are two SEPARATE consumers of PlaybookManager.
CGR3 is exposed as a standalone MCP tool (get_guidance) for external callers;
it is not invoked internally by WorkerAgent/IncrementalPlanner during
generation. This suite verifies each path for real, but does not assert one
drives the other -- see the discussion in the session this test was written
from before assuming otherwise.
"""
import shutil
import uuid
from pathlib import Path

import pytest

from src.agents.language_pod import PodSpec
from src.agents.podman_orchestrator import PodmanOrchestrator
from src.agents.podman_runner import PodmanRunner
from src.agents.python_language_pod import PythonLanguagePod
from src.agents.worker_agent import WorkerAgent
from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.audit.store import AuditStore
from src.core.curator.module import Curator
from src.core.reflector.module import Reflector
from src.playbook.manager import PlaybookManager
from src.storage.schemas import EnvironmentFeedback, GeneratorOutput, TaskInput
from src.utils.claude_cli_client import ClaudeCliClient


def _podman_available() -> bool:
    return shutil.which("podman") is not None


def _claude_cli_available() -> bool:
    return shutil.which("claude") is not None


skip_no_podman = pytest.mark.skipif(not _podman_available(), reason="podman not in PATH")
skip_no_claude_cli = pytest.mark.skipif(not _claude_cli_available(), reason="claude CLI not in PATH")


# ---------------------------------------------------------------------------
# 1. Air-gap: --network none actually blocks egress, not just claimed to.
# ---------------------------------------------------------------------------

@skip_no_podman
def test_e2e_podman_airgap_egress_blocked(shared_podman_runner):
    """A container started under PodmanOrchestrator (--network none) must not
    be able to reach the outside network at all -- proven by a real socket
    connection attempt from inside the real container, not an assertion
    about the podman run flags.
    """
    files = {
        "test_egress.py": (
            "import socket\n"
            "import pytest\n\n"
            "def test_network_egress_is_blocked():\n"
            "    with pytest.raises(OSError):\n"
            "        socket.create_connection(('8.8.8.8', 53), timeout=3).close()\n"
        )
    }
    result = shared_podman_runner.send_pulse(files)
    assert result.exit_code == 0, (
        f"egress was NOT blocked (test should have passed by catching OSError):\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert "1 passed" in result.stdout


# ---------------------------------------------------------------------------
# 2. Env exfiltration: the host process's environment must not be reachable
#    from inside the container, proven by planting a host-side secret.
# ---------------------------------------------------------------------------

@skip_no_podman
def test_e2e_podman_env_exfiltration_blocked(shared_podman_runner, monkeypatch):
    """PodmanRunner.send_pulse() shells out via `podman exec` with no `-e`
    flag and no `--env-host` -- proven here by planting a canary secret in
    the *test process's own* environment right before send_pulse() and
    verifying, from inside a real container, that it's neither in the
    container's own os.environ nor readable via /proc/1/environ (which
    would only be the host's init if the PID namespace were shared, and
    it isn't -- start() passes no --pid=host either).
    """
    monkeypatch.setenv("ACE_HOST_SECRET_CANARY", "do-not-leak-this-token")
    files = {
        "test_env_isolation.py": (
            "import os\n\n\n"
            "def test_no_host_secret_in_environ():\n"
            "    assert 'ACE_HOST_SECRET_CANARY' not in os.environ\n\n\n"
            "def test_no_host_secret_via_proc1_environ():\n"
            "    try:\n"
            "        raw = open('/proc/1/environ', 'rb').read()\n"
            "    except OSError:\n"
            "        return  # unreadable is fine too -- also proves isolation\n"
            "    assert b'ACE_HOST_SECRET_CANARY' not in raw\n"
        )
    }
    result = shared_podman_runner.send_pulse(files)
    assert result.exit_code == 0, (
        f"host secret leaked into the container:\n{result.stdout}\n{result.stderr}"
    )
    assert "2 passed" in result.stdout


# ---------------------------------------------------------------------------
# 3. Privilege escalation: --cap-drop all + the read-only workspace mount
#    must hold even though the container process is root in its own
#    (rootless-podman-remapped) user namespace -- so os.setuid(0) would be
#    a meaningless no-op here; the real invariants are CAP_SYS_ADMIN being
#    unavailable to remount, and the ro mount flag being unbypassable from
#    inside regardless of uid.
# ---------------------------------------------------------------------------

@skip_no_podman
def test_e2e_podman_privilege_escalation_blocked(shared_podman_runner):
    """A container started under PodmanOrchestrator (--cap-drop all,
    --security-opt no-new-privileges, read-only workspace mount) must
    reject both a raw remount attempt (needs CAP_SYS_ADMIN, dropped) and a
    direct write into the read-only-mounted workspace -- proven by real
    syscalls from inside a real container, not an assertion about the
    podman run flags.
    """
    files = {
        "test_privilege_escalation.py": (
            "import ctypes\n\n\n"
            "def test_remount_workspace_rw_is_blocked():\n"
            "    libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
            "    MS_REMOUNT = 32\n"
            "    ret = libc.mount(b'none', b'/workspace', None, MS_REMOUNT, None)\n"
            "    assert ret == -1\n"
            "    assert ctypes.get_errno() == 1  # EPERM: Operation not permitted\n\n\n"
            "def test_direct_write_to_readonly_workspace_is_blocked():\n"
            "    try:\n"
            "        open('/workspace/pwned.txt', 'w').write('x')\n"
            "    except OSError:\n"
            "        return\n"
            "    raise AssertionError('write to read-only workspace mount succeeded')\n"
        )
    }
    result = shared_podman_runner.send_pulse(files)
    assert result.exit_code == 0, (
        f"privilege escalation was NOT blocked:\n{result.stdout}\n{result.stderr}"
    )
    assert "2 passed" in result.stdout


# ---------------------------------------------------------------------------
# 4. Polyglot: a real RED->GREEN cycle, independently, in each language pod.
# ---------------------------------------------------------------------------

@skip_no_podman
@skip_no_claude_cli
def test_e2e_polyglot_tdd_runners(tmp_path):
    """The same trivial feature, built for real in Python, TypeScript, and
    Go -- each via its own sandboxed pod/container/toolchain, driven by a
    real LLM (ClaudeCliClient, no mocks).
    """
    from mcp_server.tools import _pod_file_paths
    from src.agents.polyglot_pod_builder import build_pod_kwargs
    from src.agents.polyglot_tdd_runner import PodFactory, PolyglotTDDRunner

    requirement = (
        "A function `add(a, b)` that returns the sum of two integers. "
        "Flat module layout: the sandbox workspace has no `src` package, so "
        "the test must import it as a top-level module (e.g. `from add import add`), "
        "never package-qualified (e.g. NOT `from src.add import add`)."
    )
    llm_client = ClaudeCliClient(timeout=180)
    src_dir = tmp_path / "src"
    test_dir = tmp_path / "tests"
    src_dir.mkdir()
    test_dir.mkdir()

    language_results = {}
    orchestrators = []
    try:
        for language in ("python", "typescript", "go"):
            test_file, impl_file = _pod_file_paths(language, "add", src_dir, test_dir)
            pod_kwargs = build_pod_kwargs(language, tmp_path, llm_client, src_dir=src_dir)
            orchestrators.append(pod_kwargs["orchestrator"])

            runner = PolyglotTDDRunner(
                PodFactory, max_cycles=2, pod_kwargs={language: pod_kwargs},
                # RED generation occasionally crashes the toolchain before it
                # writes any report (observed live for the TS/vitest leg) --
                # give it more than the default 2 attempts at a trivial spec.
                max_red_attempts=4,
            )
            result = runner.run(
                feature_requirement=requirement,
                test_file=test_file,
                implementation_file=impl_file,
                languages=[language],
            )
            language_results[language] = result.language_results[language]
    finally:
        for orchestrator in orchestrators:
            orchestrator.stop()

    for language, run_result in language_results.items():
        assert run_result.green.passed is True, (
            f"{language} never went GREEN "
            f"(cycles={run_result.cycles_to_green}): "
            f"{run_result.green.error or run_result.green.output}"
        )


# ---------------------------------------------------------------------------
# 5. Playbook learning loop: a real failure -> Reflector/Curator write a
#    bullet -> WorkerAgent picks it up on pass 2 and goes GREEN. Separately,
#    CGR3 can retrieve that same bullet (see module docstring).
# ---------------------------------------------------------------------------

@skip_no_podman
@skip_no_claude_cli
def test_e2e_playbook_learning_loop(tmp_path):
    from src.retrieval.schemas import RetrievalContext
    from src.retrieval.service import InstitutionalKnowledgeService

    requirement = "A function `add(a, b)` that returns the sum of two integers."
    llm_client = ClaudeCliClient(timeout=120)
    playbook_manager = PlaybookManager(storage_path=str(tmp_path / "playbooks"))
    playbook_id = "e2e-learning-loop"
    playbook_manager.get_or_create_playbook(playbook_id)

    orchestrator = PodmanOrchestrator(runner=PodmanRunner())
    try:
        # --- Part A.1: a REAL failure, through the REAL container -------
        # Hand-authored (not LLM-written) so the failure is deterministic:
        # a genuine, common bug (wrong operator) that a live pytest run
        # inside the sandbox will really catch.
        test_file = tmp_path / "test_add.py"
        impl_file = tmp_path / "add.py"
        test_code = (
            "from add import add\n\n"
            "def test_add_returns_sum():\n"
            "    assert add(1, 2) == 3\n"
            "    assert add(-1, 1) == 0\n"
        )
        buggy_impl = "def add(a, b):\n    return a - b\n"
        # orchestrator.pulse() only writes into the container's own transient
        # workspace, not tmp_path -- persist to the host path too, since
        # pass 2 (Part A.3 below) reads spec.test_file back off disk, same
        # as the pod itself does between RED and GREEN.
        test_file.write_text(test_code)

        failing_result = orchestrator.pulse({
            test_file.name: test_code,
            impl_file.name: buggy_impl,
        })
        assert failing_result.passed is False, "expected the buggy implementation to fail for real"

        # --- Part A.2: real Reflector + Curator analyse the real failure -
        task = TaskInput(id=f"e2e-{uuid.uuid4().hex[:8]}", query=requirement, type="tdd_cycle")
        gen_output = GeneratorOutput(
            trajectory=test_code,
            solution=buggy_impl,
            bullets_used=[],
            bullet_feedback={},
            latency_ms=0,
            tokens_used=0,
        )
        env_feedback = EnvironmentFeedback(
            result="FAILED",
            actual=failing_result.output,
            feedback=failing_result.error,
        )

        reflector = Reflector(llm_client=llm_client)
        reflector_output = reflector.reflect(task, gen_output, env_feedback)

        curator = Curator(playbook_manager=playbook_manager, llm_client=llm_client)
        curator_output = curator.curate(
            reflector_output, playbook_id, task_context={"requirement": requirement},
        )
        # curator.apply_updates() returns bullet IDs, not Bullet objects --
        # call playbook_manager.apply_delta() directly (same real persistence
        # path apply_updates() itself calls) to get the Bullet back with content.
        added_bullets = playbook_manager.apply_delta(playbook_id, curator_output.delta_bullets)
        assert len(added_bullets) >= 1, (
            f"Curator wrote no bullets from a real failure "
            f"(reflector insight: {getattr(reflector_output, 'insight', reflector_output)})"
        )
        learned_content = added_bullets[0].content

        # --- Part A.3: pass 2 -- WorkerAgent picks the bullet up, goes GREEN
        worker = WorkerAgent(llm_client, playbook_manager=playbook_manager)
        captured_prompts: list[str] = []
        real_generate = llm_client.generate

        def _spying_generate(*args, **kwargs):
            if args:
                captured_prompts.append(args[0])
            elif "prompt" in kwargs:
                captured_prompts.append(kwargs["prompt"])
            return real_generate(*args, **kwargs)

        llm_client.generate = _spying_generate
        try:
            pod = PythonLanguagePod(worker, tmp_path, orchestrator)
            spec = PodSpec(
                feature_requirement=requirement,
                test_file=test_file,
                implementation_file=impl_file,
                cycle_number=2,
            )
            green_result = pod.run_green(spec)
        finally:
            llm_client.generate = real_generate

        assert green_result.passed is True, (
            f"pass 2 never went GREEN: {green_result.error or green_result.output}"
        )
        assert any(learned_content in p for p in captured_prompts), (
            "the learned bullet's content never appeared in a pass-2 prompt -- "
            "WorkerAgent did not actually surface it"
        )
    finally:
        orchestrator.stop()

    # --- Part B: CGR3 can independently retrieve the same bullet ---------
    # Two thresholds stand between a freshly-learned bullet and a result:
    #   1. min_confidence=0.0: Curator-written bullets start at confidence 0.3
    #      (src/playbook/manager.py's apply_delta -- untrusted LLM-synthesized
    #      content), below get_guidance()'s default 0.5 filter.
    #   2. similarity_threshold=0.0: BulletRetriever's default (0.7, see
    #      settings.retrieval_similarity_threshold) is a semantic-embedding
    #      cosine similarity cutoff applied BEFORE CGR3's rank/reason step --
    #      the bullet Curator actually wrote is a general TDD-discipline
    #      lesson, not "add(a, b)"-specific, so it doesn't clear 0.7 against
    #      the narrow feature-requirement query. Zeroing it here tests CGR3's
    #      own rank/reason/verdict logic on the real candidate, rather than
    #      "did this one query happen to score above an arbitrary cutoff."
    from src.playbook.retrieval import BulletRetriever
    from src.retrieval.cgr3_retriever import ContextGraphRetriever

    service = InstitutionalKnowledgeService(
        playbook_manager=playbook_manager,
        default_playbook_id=playbook_id,
        retriever=ContextGraphRetriever(base_retriever=BulletRetriever(similarity_threshold=0.0)),
    )
    response = service.get_guidance(
        query=requirement,
        context=RetrievalContext(domain="tdd"),
        playbook_id=playbook_id,
        min_confidence=0.0,
    )
    applied_contents = [rb.bullet.content for rb in response.apply]
    all_contents = applied_contents + [rb.bullet.content for rb in response.ask_first]
    assert learned_content in all_contents, (
        f"CGR3 did not retrieve the learned bullet at all. "
        f"apply={applied_contents} ask_first={[rb.bullet.content for rb in response.ask_first]}"
    )
    assert learned_content in applied_contents, (
        f"CGR3 retrieved the bullet but did not verdict it APPLY "
        f"(landed in ask_first instead: {[q for q in response.questions]})"
    )


# ---------------------------------------------------------------------------
# 6. Tamper-evident audit chain across a complete feature-build task.
# ---------------------------------------------------------------------------

@skip_no_podman
@skip_no_claude_cli
def test_e2e_tamper_evident_audit_chain(tmp_path):
    from src.agents.tdd_cycle_runner import TDDCycleRunner

    db_path = tmp_path / "audit.db"
    audit_client = LocalAuditClient(database_url=f"sqlite:///{db_path}")

    llm_client = ClaudeCliClient(timeout=120)
    playbook_manager = PlaybookManager(storage_path=str(tmp_path / "playbooks"))
    playbook_id = "e2e-audit-chain"
    playbook_manager.get_or_create_playbook(playbook_id)

    worker = WorkerAgent(llm_client, playbook_manager=playbook_manager)
    orchestrator = PodmanOrchestrator(runner=PodmanRunner())
    try:
        pod = PythonLanguagePod(worker, tmp_path, orchestrator)
        cycle_runner = TDDCycleRunner(
            pod,
            playbook_id=playbook_id,
            audit_client=audit_client,
            reflector=Reflector(llm_client=llm_client),
            curator=Curator(playbook_manager=playbook_manager, llm_client=llm_client),
        )
        spec = PodSpec(
            feature_requirement="A function `is_even(n)` that returns True if n is even, else False.",
            test_file=tmp_path / "test_is_even.py",
            implementation_file=tmp_path / "is_even.py",
            cycle_number=1,
        )
        cycle_result = cycle_runner.run(spec)
    finally:
        orchestrator.stop()

    assert cycle_result.green_result.passed is True, (
        f"feature build never went GREEN: {cycle_result.green_result.error}"
    )

    stats = audit_client.get_stats()
    assert stats["total_events"] >= 2, f"expected multiple audit events, got {stats}"

    store = AuditStore(f"sqlite:///{db_path}")
    is_valid, first_invalid_event_id = store.verify_full_chain()
    assert is_valid is True, f"audit hash chain broken at event {first_invalid_event_id}"
