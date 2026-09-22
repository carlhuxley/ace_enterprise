"""Tests for GoLanguagePod (ace_enterprise-j5s, sandboxed in ace_enterprise-jww).

Rewritten for the sandboxed llm_client + orchestrator architecture — the pod
previously ran go/gofmt/go vet directly on the host via subprocess with no
isolation at all; it now routes through PodmanOrchestrator + GoRunner the
same way PythonLanguagePod and TypeScriptLanguagePod do.
"""
import shutil
from unittest.mock import MagicMock

import pytest

from src.agents.go_language_pod import GoLanguagePod
from src.agents.language_pod import LanguagePod, PhaseResult, PodSpec, TokenUsage
from src.agents.podman_orchestrator import PodmanOrchestrator


def make_llm_client(content="package pulse\n\nfunc Foo() {}", tokens_used=100):
    client = MagicMock()
    client.generate.return_value = {
        "content": content,
        "tokens_used": tokens_used,
        "latency_ms": 40,
        "model": "gpt-4o",
    }
    return client


def make_pod(tmp_path, playbook_manager=None, pulse_result=None, retrieval_service=None, llm_client=None):
    orchestrator = MagicMock()
    orchestrator.pulse.return_value = pulse_result or PhaseResult(
        passed=True, output="ok", error=None
    )
    return GoLanguagePod(
        llm_client=llm_client or make_llm_client(),
        project_root=tmp_path,
        orchestrator=orchestrator,
        playbook_manager=playbook_manager,
        retrieval_service=retrieval_service,
    )


def spec(tmp_path, cycle=1):
    return PodSpec(
        feature_requirement="User authentication with JWT",
        test_file=tmp_path / "auth_test.go",
        implementation_file=tmp_path / "auth.go",
        cycle_number=cycle,
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestProtocolConformance:
    def test_isinstance_language_pod(self, tmp_path):
        pod = make_pod(tmp_path)
        assert isinstance(pod, LanguagePod)

    def test_has_all_required_methods(self, tmp_path):
        pod = make_pod(tmp_path)
        assert callable(pod.run_red)
        assert callable(pod.run_green)
        assert callable(pod.run_refactor)
        assert callable(pod.token_usage)


# ---------------------------------------------------------------------------
# run_red
# ---------------------------------------------------------------------------

class TestRunRed:
    def test_returns_phase_result(self, tmp_path):
        pod = make_pod(tmp_path)
        result = pod.run_red(spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_writes_test_file(self, tmp_path):
        pod = make_pod(tmp_path)
        s = spec(tmp_path)
        pod.run_red(s)
        assert s.test_file.exists()

    def test_calls_orchestrator_pulse(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_red(spec(tmp_path))
        pod._orchestrator.pulse.assert_called_once()

    def test_passed_false_when_pulse_fails(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=False, output="FAIL", error=None))
        result = pod.run_red(spec(tmp_path))
        assert not result.passed

    def test_passed_true_when_pulse_passes(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=True, output="ok", error=None))
        result = pod.run_red(spec(tmp_path))
        assert result.passed

    def test_llm_exception_returns_failed_result(self, tmp_path):
        client = MagicMock()
        client.generate.side_effect = RuntimeError("LLM unavailable")
        orchestrator = MagicMock()
        pod = GoLanguagePod(llm_client=client, project_root=tmp_path, orchestrator=orchestrator)
        result = pod.run_red(spec(tmp_path))
        assert not result.passed
        assert result.error is not None
        orchestrator.pulse.assert_not_called()

    def test_security_gate_failure_does_not_commit_test_file(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(
            passed=False, output="", error="Security gate: HIGH=1 MEDIUM=0 LOW=0"
        ))
        s = spec(tmp_path)
        pod.run_red(s)
        assert not s.test_file.exists()


# ---------------------------------------------------------------------------
# run_green
# ---------------------------------------------------------------------------

class TestRunGreen:
    def test_returns_phase_result(self, tmp_path):
        pod = make_pod(tmp_path)
        result = pod.run_green(spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_writes_implementation_file_when_pulse_passes(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=True, output="ok", error=None))
        s = spec(tmp_path)
        pod.run_green(s)
        assert s.implementation_file.exists()

    def test_does_not_write_implementation_file_when_pulse_fails(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=False, output="FAIL", error=None))
        s = spec(tmp_path)
        pod.run_green(s)
        assert not s.implementation_file.exists()

    def test_passed_when_pulse_passes(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=True, output="ok", error=None))
        result = pod.run_green(spec(tmp_path))
        assert result.passed

    def test_failed_when_pulse_fails(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=False, output="FAIL", error=None))
        result = pod.run_green(spec(tmp_path))
        assert not result.passed

    def test_queries_playbook_for_go_bullets(self, tmp_path):
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("b1", "use errors.New for sentinel errors")]
        pod = make_pod(tmp_path, playbook_manager=pm)
        pod.run_green(spec(tmp_path))
        pm.get_bullets_with_ids.assert_called_once_with("global-go-bullets")

    def test_no_error_when_no_playbook(self, tmp_path):
        pod = make_pod(tmp_path, playbook_manager=None)
        result = pod.run_green(spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_attaches_retrieved_bullet_ids_to_result(self, tmp_path):
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("b1", "use errors.New for sentinel errors")]
        pod = make_pod(tmp_path, playbook_manager=pm)
        result = pod.run_green(spec(tmp_path))
        assert result.retrieved_bullet_ids == ["b1"]

    def test_retrieved_bullet_ids_empty_when_no_playbook(self, tmp_path):
        pod = make_pod(tmp_path, playbook_manager=None)
        result = pod.run_green(spec(tmp_path))
        assert result.retrieved_bullet_ids == []

    def test_retrieval_service_present_uses_its_apply_list_not_the_full_playbook(self, tmp_path):
        # ace_enterprise#66: a configured retrieval_service (CGR3) takes
        # priority over the unconditional get_bullets_with_ids() dump, even
        # when a playbook_manager is ALSO set.
        from src.retrieval.schemas import KnowledgeResponse, RankedBullet
        from src.storage.schemas import Bullet

        applied_bullet = Bullet(
            id="ctx-001", section="global-go-bullets", content="use context.Context for cancellation",
            created_at="2026-01-01T00:00:00", tags=[],
        )
        response = KnowledgeResponse(
            apply=[RankedBullet(bullet=applied_bullet, semantic_score=0.9, context_score=0.8, combined_score=0.85)],
        )
        service = MagicMock()
        service.get_guidance_for_implementation.return_value = response
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("ctx-999", "irrelevant bullet from the full dump")]

        client = make_llm_client()
        original_generate = client.generate  # _intercept_tokens replaces client.generate itself
        pod = make_pod(tmp_path, playbook_manager=pm, retrieval_service=service, llm_client=client)
        result = pod.run_green(spec(tmp_path))

        assert result.retrieved_bullet_ids == ["ctx-001"]
        prompt = original_generate.call_args[0][0]
        assert "use context.Context for cancellation" in prompt
        assert "irrelevant bullet from the full dump" not in prompt
        pm.get_bullets_with_ids.assert_not_called()

    def test_retrieval_service_passes_the_feature_requirement_as_the_query(self, tmp_path):
        from src.retrieval.schemas import KnowledgeResponse

        service = MagicMock()
        service.get_guidance_for_implementation.return_value = KnowledgeResponse()
        pod = make_pod(tmp_path, retrieval_service=service)
        pod.run_green(spec(tmp_path))
        service.get_guidance_for_implementation.assert_called_once_with("User authentication with JWT")

    def test_retrieval_service_empty_apply_falls_back_to_default_bullets(self, tmp_path):
        # Unlike SimulationPod, _DEFAULT_GO_BULLETS are universal idioms
        # meant to apply regardless of task-specific relevance, so an empty
        # CGR3 result still falls back to them.
        from src.retrieval.schemas import KnowledgeResponse

        service = MagicMock()
        service.get_guidance_for_implementation.return_value = KnowledgeResponse(apply=[])
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("ctx-999", "should not be used")]

        client = make_llm_client()
        original_generate = client.generate  # _intercept_tokens replaces client.generate itself
        pod = make_pod(tmp_path, playbook_manager=pm, retrieval_service=service, llm_client=client)
        result = pod.run_green(spec(tmp_path))

        assert result.retrieved_bullet_ids == []
        prompt = original_generate.call_args[0][0]
        assert "should not be used" not in prompt
        pm.get_bullets_with_ids.assert_not_called()

    def test_retrieval_service_failure_falls_back_to_the_full_playbook_dump(self, tmp_path):
        service = MagicMock()
        service.get_guidance_for_implementation.side_effect = RuntimeError("embedding service down")
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("ctx-1", "fallback bullet")]

        client = make_llm_client()
        original_generate = client.generate  # _intercept_tokens replaces client.generate itself
        pod = make_pod(tmp_path, playbook_manager=pm, retrieval_service=service, llm_client=client)
        result = pod.run_green(spec(tmp_path))

        assert result.retrieved_bullet_ids == ["ctx-1"]
        prompt = original_generate.call_args[0][0]
        assert "fallback bullet" in prompt

    def test_no_retrieval_service_configured_uses_the_full_playbook_dump_unchanged(self, tmp_path):
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("ctx-1", "the old behavior")]
        client = make_llm_client()
        original_generate = client.generate  # _intercept_tokens replaces client.generate itself
        pod = make_pod(tmp_path, playbook_manager=pm, llm_client=client)
        pod.run_green(spec(tmp_path))
        prompt = original_generate.call_args[0][0]
        assert "the old behavior" in prompt


# ---------------------------------------------------------------------------
# run_refactor
# ---------------------------------------------------------------------------

class TestRunRefactor:
    def test_returns_phase_result(self, tmp_path):
        pod = make_pod(tmp_path)
        result = pod.run_refactor(spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_does_not_call_llm(self, tmp_path):
        """Matches the pre-existing, deliberate design: REFACTOR uses
        deterministic gofmt/go vet, not an LLM call (see ace_enterprise-3dg,
        which explicitly left this alone as intentional and correct)."""
        client = make_llm_client()
        original_generate = client.generate  # _intercept_tokens replaces client.generate itself
        orchestrator = MagicMock()
        orchestrator.pulse.return_value = PhaseResult(passed=True, output="ok", error=None)
        pod = GoLanguagePod(llm_client=client, project_root=tmp_path, orchestrator=orchestrator)
        pod.run_refactor(spec(tmp_path))
        original_generate.assert_not_called()

    def test_passed_when_pulse_passes(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=True, output="ok", error=None))
        result = pod.run_refactor(spec(tmp_path))
        assert result.passed

    def test_failed_when_pulse_fails(self, tmp_path):
        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=False, output="FAIL", error=None))
        result = pod.run_refactor(spec(tmp_path))
        assert not result.passed

    def test_commits_gofmt_formatted_output_when_present(self, tmp_path):
        s = spec(tmp_path)
        s.implementation_file.parent.mkdir(parents=True, exist_ok=True)
        s.implementation_file.write_text("package pulse\nfunc Foo(){return}")

        pod = make_pod(tmp_path, pulse_result=PhaseResult(
            passed=True, output="ok", error=None,
            formatted_files={s.implementation_file.name: "package pulse\n\nfunc Foo() { return }\n"},
        ))
        pod.run_refactor(s)

        assert s.implementation_file.read_text() == "package pulse\n\nfunc Foo() { return }\n"

    def test_does_not_clobber_impl_when_refactor_pulse_fails(self, tmp_path):
        s = spec(tmp_path)
        s.implementation_file.parent.mkdir(parents=True, exist_ok=True)
        s.implementation_file.write_text("package pulse\nfunc Foo(){return}")

        pod = make_pod(tmp_path, pulse_result=PhaseResult(
            passed=False, output="FAIL", error=None,
            formatted_files={s.implementation_file.name: "package pulse\n\nfunc Foo() { return }\n"},
        ))
        pod.run_refactor(s)

        assert s.implementation_file.read_text() == "package pulse\nfunc Foo(){return}"

    def test_no_formatted_files_leaves_impl_unchanged(self, tmp_path):
        s = spec(tmp_path)
        s.implementation_file.parent.mkdir(parents=True, exist_ok=True)
        s.implementation_file.write_text("package pulse\nfunc Foo(){return}")

        pod = make_pod(tmp_path, pulse_result=PhaseResult(passed=True, output="ok", error=None))
        pod.run_refactor(s)

        assert s.implementation_file.read_text() == "package pulse\nfunc Foo(){return}"


# ---------------------------------------------------------------------------
# token_usage
# ---------------------------------------------------------------------------

class TestTokenUsage:
    def test_returns_list(self, tmp_path):
        pod = make_pod(tmp_path)
        assert isinstance(pod.token_usage(), list)

    def test_empty_before_any_phase(self, tmp_path):
        pod = make_pod(tmp_path)
        assert pod.token_usage() == []

    def test_records_usage_after_red(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_red(spec(tmp_path, cycle=1))
        usage = pod.token_usage()
        assert len(usage) == 1
        assert usage[0].cycle_number == 1
        assert usage[0].input_tokens == 100

    def test_accumulates_across_cycles(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_red(spec(tmp_path, cycle=1))
        pod.run_red(spec(tmp_path, cycle=2))
        assert len(pod.token_usage()) == 2
        assert pod.token_usage()[0].cycle_number == 1
        assert pod.token_usage()[1].cycle_number == 2

    def test_token_usage_entries_are_token_usage_type(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_red(spec(tmp_path, cycle=1))
        assert all(isinstance(u, TokenUsage) for u in pod.token_usage())

    def test_refactor_records_zero_llm_tokens(self, tmp_path):
        pod = make_pod(tmp_path)
        pod.run_refactor(spec(tmp_path, cycle=1))
        usage = pod.token_usage()
        assert len(usage) == 1
        assert usage[0].input_tokens == 0


# ---------------------------------------------------------------------------
# Integration: real Podman container, real Go toolchain, real gosec
# ---------------------------------------------------------------------------

skip_no_podman = pytest.mark.skipif(
    shutil.which("podman") is None, reason="podman not in PATH"
)


@pytest.fixture(scope="module")
def go_runner():
    if shutil.which("podman") is None:
        pytest.skip("podman not in PATH")
    from src.agents.go_runner import GoRunner
    runner = GoRunner(container_name="go_language_pod_test_session")
    runner.start()
    yield runner
    runner.stop()


_SAFE_GO_TEST = (
    "package pulse\n\n"
    "import \"testing\"\n\n"
    "func TestAdd(t *testing.T) {\n"
    "\tif Add(1, 2) != 3 {\n"
    "\t\tt.Errorf(\"expected 3\")\n"
    "\t}\n"
    "}\n"
)
_SAFE_GO_IMPL = "package pulse\n\n// Add returns the sum of a and b.\nfunc Add(a, b int) int {\n\treturn a + b\n}\n"

_VULN_GO_IMPL = (
    "package pulse\n\n"
    "import \"os\"\n"
    "import \"os/exec\"\n\n"
    "func Run() error {\n"
    "\tcmd := exec.Command(os.Getenv(\"CMD\"))\n"
    "\treturn cmd.Run()\n"
    "}\n"
)
_VULN_GO_TEST = (
    "package pulse\n\n"
    "import \"testing\"\n\n"
    "func TestRun(t *testing.T) {\n"
    "\t_ = Run\n"
    "}\n"
)


@skip_no_podman
class TestGoIntegration:
    def test_safe_code_passes_full_sandwich(self, go_runner, tmp_path):
        orchestrator = PodmanOrchestrator(runner=go_runner, work_dir=tmp_path / "work")
        client = make_llm_client(content=_SAFE_GO_TEST)
        pod = GoLanguagePod(llm_client=client, project_root=tmp_path, orchestrator=orchestrator)
        s = spec(tmp_path)
        s.implementation_file.write_text(_SAFE_GO_IMPL)

        result = pod.run_red(s)

        assert result.passed is True
        assert s.test_file.exists()

    def test_vulnerable_code_blocked_by_gosec(self, go_runner, tmp_path):
        orchestrator = PodmanOrchestrator(runner=go_runner, work_dir=tmp_path / "work")
        client = make_llm_client(content=_VULN_GO_IMPL)
        pod = GoLanguagePod(llm_client=client, project_root=tmp_path, orchestrator=orchestrator)
        s = spec(tmp_path)
        s.test_file.write_text(_VULN_GO_TEST)

        result = pod.run_green(s)

        assert result.passed is False
        assert result.error is not None and result.error.startswith("Security gate:")
        assert not s.implementation_file.exists()

    def test_refactor_applies_real_gofmt_formatting(self, go_runner, tmp_path):
        orchestrator = PodmanOrchestrator(runner=go_runner, work_dir=tmp_path / "work")
        pod = GoLanguagePod(llm_client=make_llm_client(), project_root=tmp_path, orchestrator=orchestrator)
        s = spec(tmp_path)
        s.test_file.write_text(_SAFE_GO_TEST)
        s.implementation_file.write_text(
            "package pulse\n\n// Add returns the sum of a and b.\nfunc Add(a, b int) int {\nreturn a+b\n}\n"
        )

        result = pod.run_refactor(s)

        assert result.passed is True
        reformatted = s.implementation_file.read_text()
        assert reformatted == (
            "package pulse\n\n// Add returns the sum of a and b.\nfunc Add(a, b int) int {\n\treturn a + b\n}\n"
        )
