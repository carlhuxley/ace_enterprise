"""Tests for WorkerAgent and PythonLanguagePod (ace_enterprise-eyd)."""
from unittest.mock import MagicMock

from src.agents.language_pod import LanguagePod, PhaseResult, PodSpec
from src.agents.worker_agent import WorkerAgent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _llm(content="def test_foo(): pass", tokens=80):
    client = MagicMock()
    client.generate.return_value = {
        "content": content,
        "tokens_used": tokens,
        "latency_ms": 20,
        "model": "gpt-4o",
    }
    return client


def _spec(tmp_path, cycle=1):
    return PodSpec(
        feature_requirement="Process an order",
        test_file=tmp_path / "test_order.py",
        implementation_file=tmp_path / "order.py",
        cycle_number=cycle,
    )


def _captured_prompt(worker):
    """Return the prompt string passed to the last generate() call."""
    return worker.llm_client.generate.call_args[0][0]


# ---------------------------------------------------------------------------
# WorkerAgent — generate_test
# ---------------------------------------------------------------------------

class TestGenerateTest:
    def test_returns_string(self, tmp_path):
        w = WorkerAgent(_llm())
        assert isinstance(w.generate_test(_spec(tmp_path)), str)

    def test_calls_llm_once(self, tmp_path):
        client = _llm()
        w = WorkerAgent(client)
        w.generate_test(_spec(tmp_path))
        client.generate.assert_called_once()

    def test_prompt_includes_feature_requirement(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_test(_spec(tmp_path))
        assert "Process an order" in _captured_prompt(w)

    def test_prompt_includes_existing_code_when_provided(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_test(_spec(tmp_path), existing_code="def test_existing(): pass")
        assert "test_existing" in _captured_prompt(w)

    def test_prompt_excludes_existing_code_section_when_empty(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_test(_spec(tmp_path), existing_code="")
        prompt = _captured_prompt(w)
        assert "Existing tests" not in prompt

    def test_strips_markdown_fences_from_response(self, tmp_path):
        w = WorkerAgent(_llm(content="```python\ndef test_foo(): pass\n```"))
        result = w.generate_test(_spec(tmp_path))
        assert result == "def test_foo(): pass"

    def test_prompt_warns_about_blocked_sandbox_imports(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_test(_spec(tmp_path))
        prompt = _captured_prompt(w)
        assert "os" in prompt and "subprocess" in prompt and "pathlib.Path" in prompt


# ---------------------------------------------------------------------------
# WorkerAgent — generate_implementation
# ---------------------------------------------------------------------------

class TestGenerateImplementation:
    def test_returns_string(self, tmp_path):
        w = WorkerAgent(_llm(content="def process(): pass"))
        assert isinstance(w.generate_implementation(_spec(tmp_path)), str)

    def test_prompt_includes_feature_requirement(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_implementation(_spec(tmp_path))
        assert "Process an order" in _captured_prompt(w)

    def test_prompt_includes_error_output_when_provided(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_implementation(_spec(tmp_path), error_output="AssertionError: expected 1 got 0")
        assert "AssertionError" in _captured_prompt(w)

    def test_prompt_excludes_error_section_when_empty(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_implementation(_spec(tmp_path))
        assert "Test failure" not in _captured_prompt(w)

    def test_prompt_includes_module_context_when_provided(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_implementation(_spec(tmp_path), module_context="def inventory_check() -> bool")
        assert "inventory_check" in _captured_prompt(w)

    def test_playbook_bullets_injected_when_manager_set(self, tmp_path):
        pm = MagicMock()
        pm.get_bullets.return_value = ["always validate inputs at boundaries"]
        w = WorkerAgent(_llm(), playbook_manager=pm)
        w.generate_implementation(_spec(tmp_path))
        assert "always validate inputs at boundaries" in _captured_prompt(w)

    def test_no_bullets_section_when_no_playbook(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_implementation(_spec(tmp_path))
        assert "Playbook" not in _captured_prompt(w)

    def test_prompt_warns_about_blocked_sandbox_imports(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_implementation(_spec(tmp_path))
        assert "SANDBOX:" in _captured_prompt(w)

    def test_context_map_queried_with_failing_test_ids(self, tmp_path):
        cm = MagicMock()
        sig = MagicMock()
        sig.format_compact.return_value = "def process_order(cart: Cart) -> Order"
        cm.nodes_relevant_to.return_value = [sig]

        w = WorkerAgent(_llm(), context_map=cm)
        w.generate_implementation(
            _spec(tmp_path),
            failing_test_ids=["test_order.py::test_process_order"],
        )
        cm.nodes_relevant_to.assert_called_once_with(["test_order.py::test_process_order"])
        assert "process_order" in _captured_prompt(w)

    def test_context_map_skipped_when_no_failing_test_ids(self, tmp_path):
        cm = MagicMock()
        w = WorkerAgent(_llm(), context_map=cm)
        w.generate_implementation(_spec(tmp_path))
        cm.nodes_relevant_to.assert_not_called()


# ---------------------------------------------------------------------------
# WorkerAgent — generate_refactor
# ---------------------------------------------------------------------------

class TestGenerateRefactor:
    def test_returns_string(self, tmp_path):
        w = WorkerAgent(_llm(content="def process(): return True"))
        assert isinstance(w.generate_refactor(_spec(tmp_path)), str)

    def test_calls_llm_once(self, tmp_path):
        client = _llm()
        w = WorkerAgent(client)
        w.generate_refactor(_spec(tmp_path))
        client.generate.assert_called_once()

    def test_prompt_includes_current_code_when_provided(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_refactor(_spec(tmp_path), current_code="def process(): return 1")
        assert "def process(): return 1" in _captured_prompt(w)

    def test_prompt_includes_feature_requirement(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_refactor(_spec(tmp_path))
        assert "Process an order" in _captured_prompt(w)


# ---------------------------------------------------------------------------
# PythonLanguagePod (worker + orchestrator construction)
# ---------------------------------------------------------------------------

class TestPythonLanguagePodFromWorker:
    def _make_pod(self, tmp_path, content="def test_foo(): pass", green_passed=True):
        from src.agents.python_language_pod import PythonLanguagePod
        worker = WorkerAgent(_llm(content=content))
        orchestrator = MagicMock()
        # RED: pytest fails (correct TDD), no security error → test file committed
        # GREEN: pytest passes → impl file committed
        orchestrator.pulse.return_value = PhaseResult(
            passed=green_passed,
            output="1 passed" if green_passed else "FAILED",
            error=None,
        )
        return PythonLanguagePod(worker, project_root=tmp_path, orchestrator=orchestrator), worker

    def test_isinstance_language_pod(self, tmp_path):
        pod, _ = self._make_pod(tmp_path)
        assert isinstance(pod, LanguagePod)

    def test_run_red_returns_phase_result(self, tmp_path):
        pod, _ = self._make_pod(tmp_path, green_passed=False)
        result = pod.run_red(_spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_run_red_writes_test_file(self, tmp_path):
        pod, _ = self._make_pod(tmp_path, green_passed=False)
        s = _spec(tmp_path)
        pod.run_red(s)
        assert s.test_file.exists()

    def test_run_green_returns_phase_result(self, tmp_path):
        pod, _ = self._make_pod(tmp_path, content="def process(): pass", green_passed=True)
        result = pod.run_green(_spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_run_green_writes_implementation_file(self, tmp_path):
        pod, _ = self._make_pod(tmp_path, content="def process(): pass", green_passed=True)
        s = _spec(tmp_path)
        pod.run_green(s)
        assert s.implementation_file.exists()

    def test_run_refactor_returns_phase_result(self, tmp_path):
        pod, _ = self._make_pod(tmp_path, green_passed=True)
        result = pod.run_refactor(_spec(tmp_path))
        assert isinstance(result, PhaseResult)

    def test_token_usage_tracks_llm_calls(self, tmp_path):
        from src.agents.language_pod import TokenUsage
        pod, _ = self._make_pod(tmp_path, green_passed=False)
        pod.run_red(_spec(tmp_path, cycle=1))
        usage = pod.token_usage()
        assert len(usage) == 1
        assert isinstance(usage[0], TokenUsage)
        assert usage[0].input_tokens == 80
