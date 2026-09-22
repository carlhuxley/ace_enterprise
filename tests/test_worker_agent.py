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

    def test_prompt_states_the_flat_import_convention_for_this_module(self, tmp_path):
        # Neither prompt builder used to state any import convention for
        # sibling modules at all, so the model guessed -- often a `src.`-
        # qualified path that doesn't exist in this project's flat layout,
        # failing every GREEN at pytest collection with no way to recover
        # since the same guess just repeats.
        w = WorkerAgent(_llm())
        w.generate_test(_spec(tmp_path))
        prompt = _captured_prompt(w)
        assert "from order import" in prompt
        assert "from src.order import" in prompt  # named as the wrong example
        assert "flat" in prompt.lower()


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
        pm.get_bullets_with_ids.return_value = [("b1", "always validate inputs at boundaries")]
        w = WorkerAgent(_llm(), playbook_manager=pm)
        w.generate_implementation(_spec(tmp_path))
        assert "always validate inputs at boundaries" in _captured_prompt(w)

    def test_no_bullets_section_when_no_playbook(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_implementation(_spec(tmp_path))
        assert "Playbook" not in _captured_prompt(w)

    def test_records_last_retrieved_bullet_ids(self, tmp_path):
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("b1", "one"), ("b2", "two")]
        w = WorkerAgent(_llm(), playbook_manager=pm)
        w.generate_implementation(_spec(tmp_path))
        assert w.last_retrieved_bullet_ids == ["b1", "b2"]

    def test_last_retrieved_bullet_ids_empty_when_no_playbook(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_implementation(_spec(tmp_path))
        assert w.last_retrieved_bullet_ids == []

    def test_retrieval_service_present_uses_its_apply_list_not_the_full_playbook(self, tmp_path):
        # ace_enterprise#66: a configured retrieval_service (CGR3) takes
        # priority over the unconditional get_bullets_with_ids() dump, even
        # when a playbook_manager is ALSO set.
        from src.retrieval.schemas import KnowledgeResponse, RankedBullet
        from src.storage.schemas import Bullet

        applied_bullet = Bullet(
            id="ctx-001", section="strategies_and_hard_rules", content="use pathlib",
            created_at="2026-01-01T00:00:00", tags=[],
        )
        response = KnowledgeResponse(
            apply=[RankedBullet(bullet=applied_bullet, semantic_score=0.9, context_score=0.8, combined_score=0.85)],
        )
        service = MagicMock()
        service.get_guidance_for_implementation.return_value = response
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("ctx-999", "irrelevant bullet from the full dump")]

        w = WorkerAgent(_llm(), playbook_manager=pm, retrieval_service=service)
        w.generate_implementation(_spec(tmp_path))

        assert w.last_retrieved_bullet_ids == ["ctx-001"]
        assert "use pathlib" in _captured_prompt(w)
        assert "irrelevant bullet from the full dump" not in _captured_prompt(w)
        pm.get_bullets_with_ids.assert_not_called()

    def test_retrieval_service_passes_the_feature_requirement_as_the_query(self, tmp_path):
        from src.retrieval.schemas import KnowledgeResponse

        service = MagicMock()
        service.get_guidance_for_implementation.return_value = KnowledgeResponse()
        w = WorkerAgent(_llm(), retrieval_service=service)
        w.generate_implementation(_spec(tmp_path))
        service.get_guidance_for_implementation.assert_called_once_with("Process an order")

    def test_retrieval_service_empty_apply_is_a_real_answer_not_a_fallback_trigger(self, tmp_path):
        # CGR3 running and finding nothing applicable is meaningful --
        # must NOT silently fall back to dumping the whole playbook.
        from src.retrieval.schemas import KnowledgeResponse

        service = MagicMock()
        service.get_guidance_for_implementation.return_value = KnowledgeResponse(apply=[])
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("ctx-999", "should not be used")]

        w = WorkerAgent(_llm(), playbook_manager=pm, retrieval_service=service)
        w.generate_implementation(_spec(tmp_path))

        assert w.last_retrieved_bullet_ids == []
        assert "should not be used" not in _captured_prompt(w)
        pm.get_bullets_with_ids.assert_not_called()

    def test_retrieval_service_failure_falls_back_to_the_full_playbook_dump(self, tmp_path):
        service = MagicMock()
        service.get_guidance_for_implementation.side_effect = RuntimeError("embedding service down")
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("ctx-1", "fallback bullet")]

        w = WorkerAgent(_llm(), playbook_manager=pm, retrieval_service=service)
        w.generate_implementation(_spec(tmp_path))

        assert w.last_retrieved_bullet_ids == ["ctx-1"]
        assert "fallback bullet" in _captured_prompt(w)

    def test_no_retrieval_service_configured_uses_the_full_playbook_dump_unchanged(self, tmp_path):
        # Backward compatibility: retrieval_service defaults to None, so
        # every existing caller that never sets it keeps today's behavior.
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("ctx-1", "the old behavior")]
        w = WorkerAgent(_llm(), playbook_manager=pm)
        w.generate_implementation(_spec(tmp_path))
        assert "the old behavior" in _captured_prompt(w)

    def test_prompt_warns_about_blocked_sandbox_imports(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_implementation(_spec(tmp_path))
        assert "SANDBOX:" in _captured_prompt(w)

    def test_prompt_states_the_flat_import_convention_for_this_module(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_implementation(_spec(tmp_path))
        prompt = _captured_prompt(w)
        assert "from order import" in prompt
        assert "from src.order import" in prompt  # named as the wrong example
        assert "flat" in prompt.lower()

    def test_no_existing_code_prompts_a_fresh_implementation(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_implementation(_spec(tmp_path))
        prompt = _captured_prompt(w)
        assert "minimal implementation" in prompt
        assert "Existing module" not in prompt

    def test_existing_code_prompts_an_extension_not_a_rewrite(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_implementation(
            _spec(tmp_path),
            existing_code="import json\n\ndef parse(s):\n    return json.loads(s)\n",
        )
        prompt = _captured_prompt(w)
        assert "Extend the EXISTING module" in prompt
        assert "do NOT rewrite it" in prompt
        assert "def parse(s):" in prompt  # the current code is shown

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

    def test_prompt_states_the_flat_import_convention_for_this_module(self, tmp_path):
        w = WorkerAgent(_llm())
        w.generate_refactor(_spec(tmp_path))
        prompt = _captured_prompt(w)
        assert "from order import" in prompt
        assert "flat" in prompt.lower()


# ---------------------------------------------------------------------------
# WorkerAgent — generate_patch (#53 diff-based-editing follow-up)
# ---------------------------------------------------------------------------

_SR_BLOCK = "<<<<<<< SEARCH\nreturn 1\n=======\nreturn 2\n>>>>>>> REPLACE"


class TestGeneratePatch:
    def test_returns_raw_content_not_code_extracted(self, tmp_path):
        """Unlike generate_test/generate_implementation/generate_refactor,
        the payload is SEARCH/REPLACE markers, not a source file -- it must
        come back verbatim, not run through the ```python fence extractor."""
        w = WorkerAgent(_llm(content=_SR_BLOCK))
        result = w.generate_patch(_spec(tmp_path), existing_code="def foo():\n    return 1\n")
        assert result == _SR_BLOCK

    def test_calls_llm_once(self, tmp_path):
        client = _llm(content=_SR_BLOCK)
        w = WorkerAgent(client)
        w.generate_patch(_spec(tmp_path), existing_code="def foo():\n    return 1\n")
        client.generate.assert_called_once()

    def test_prompt_includes_existing_code(self, tmp_path):
        w = WorkerAgent(_llm(content=_SR_BLOCK))
        w.generate_patch(_spec(tmp_path), existing_code="def foo():\n    return 1\n")
        assert "def foo():\n    return 1" in _captured_prompt(w)

    def test_prompt_includes_error_output_when_provided(self, tmp_path):
        w = WorkerAgent(_llm(content=_SR_BLOCK))
        w.generate_patch(
            _spec(tmp_path), existing_code="x = 1", error_output="AssertionError: boom",
        )
        assert "AssertionError: boom" in _captured_prompt(w)

    def test_prompt_includes_test_code_when_provided(self, tmp_path):
        w = WorkerAgent(_llm(content=_SR_BLOCK))
        w.generate_patch(_spec(tmp_path), existing_code="x = 1", test_code="def test_x(): assert x == 1")
        assert "def test_x(): assert x == 1" in _captured_prompt(w)

    def test_prompt_instructs_search_replace_format_not_whole_file(self, tmp_path):
        w = WorkerAgent(_llm(content=_SR_BLOCK))
        w.generate_patch(_spec(tmp_path), existing_code="x = 1")
        prompt = _captured_prompt(w)
        assert "SEARCH/REPLACE" in prompt
        assert "do NOT output the whole file" in prompt

    def test_prompt_states_the_flat_import_convention_for_this_module(self, tmp_path):
        w = WorkerAgent(_llm(content=_SR_BLOCK))
        w.generate_patch(_spec(tmp_path), existing_code="x = 1")
        prompt = _captured_prompt(w)
        assert "from order import" in prompt
        assert "flat" in prompt.lower()

    def test_prompt_includes_playbook_bullets(self, tmp_path):
        pm = MagicMock()
        pm.get_bullets_with_ids.return_value = [("b1", "always validate input")]
        w = WorkerAgent(_llm(content=_SR_BLOCK), playbook_manager=pm)
        w.generate_patch(_spec(tmp_path), existing_code="x = 1")
        assert "always validate input" in _captured_prompt(w)


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

    def _pod_with_captured_llm(self, tmp_path):
        """A pod whose LLM mock we can still inspect after the pod's
        _intercept_tokens wrapper reassigns llm_client.generate."""
        from src.agents.python_language_pod import PythonLanguagePod
        client = _llm(content="def process(): pass")
        original_generate = client.generate  # grab before the pod wraps it
        orch = MagicMock()
        orch.pulse.return_value = PhaseResult(passed=True, output="1 passed", error=None)
        pod = PythonLanguagePod(WorkerAgent(client), project_root=tmp_path, orchestrator=orch)
        return pod, original_generate

    def test_run_green_feeds_the_existing_impl_into_the_prompt(self, tmp_path):
        pod, generate = self._pod_with_captured_llm(tmp_path)
        s = _spec(tmp_path)
        s.implementation_file.write_text("import math\n\ndef area(r):\n    return math.pi * r * r\n")
        pod.run_green(s)
        prompt = generate.call_args[0][0]
        assert "def area(r):" in prompt
        assert "Extend the EXISTING module" in prompt

    def test_run_green_no_prior_impl_prompts_fresh(self, tmp_path):
        pod, generate = self._pod_with_captured_llm(tmp_path)
        pod.run_green(_spec(tmp_path))  # no impl file on disk yet
        prompt = generate.call_args[0][0]
        assert "Existing module" not in prompt

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
