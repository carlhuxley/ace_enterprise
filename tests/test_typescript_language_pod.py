"""Tests for TypeScriptLanguagePod's multi-file GREEN (follow-up to
ace_enterprise#64/#68). No dedicated test file existed for this pod before
this -- it was previously only exercised indirectly via
tests/test_polyglot_pod_builder.py, tests/test_polyglot_tdd_runner.py, and
tests/test_mcp_build_feature_language.py.
"""
from unittest.mock import MagicMock

from src.agents.language_pod import LanguagePod, PhaseResult, PodSpec
from src.agents.typescript_language_pod import TypeScriptLanguagePod


def make_worker():
    worker = MagicMock()
    worker.llm_client = MagicMock()
    worker.llm_client.generate.return_value = {
        "content": "x", "prompt_tokens": 10, "completion_tokens": 0,
        "tokens_used": 10, "latency_ms": 5, "model": "gpt-4o",
    }
    worker.last_retrieved_bullet_ids = ["b1"]
    return worker


def make_pod(tmp_path, worker=None, pulse_result=None, patch_escalation_threshold=2):
    orchestrator = MagicMock()
    orchestrator.pulse.return_value = pulse_result or PhaseResult(
        passed=True, output="1 passed", error=None
    )
    return TypeScriptLanguagePod(
        worker or make_worker(), tmp_path, orchestrator,
        patch_escalation_threshold=patch_escalation_threshold,
    )


def spec(tmp_path, cycle=1):
    return PodSpec(
        feature_requirement="Process an order",
        test_file=tmp_path / "order.test.ts",
        implementation_file=tmp_path / "order.ts",
        cycle_number=cycle,
    )


def make_multi_file_spec(tmp_path, cycle=1):
    s = spec(tmp_path, cycle=cycle)
    s.extra_target_files = [tmp_path / "helpers.ts"]
    return s


def _write_multi_file_ts_targets(s: PodSpec) -> None:
    s.implementation_file.parent.mkdir(parents=True, exist_ok=True)
    s.implementation_file.write_text("export function foo(): void {}\n", encoding="utf-8")
    for extra in s.extra_target_files:
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text("export {};\n", encoding="utf-8")


_MULTI_FILE_TS_SR_BLOCK = (
    "### FILE: order.ts\n"
    "<<<<<<< SEARCH\n"
    "export function foo(): void {}\n"
    "=======\n"
    "export function foo(): void { bar(); }\n"
    ">>>>>>> REPLACE\n\n"
    "### FILE: helpers.ts\n"
    "<<<<<<< SEARCH\n"
    "export {};\n"
    "=======\n"
    "export {};\nexport function bar(): void {}\n"
    ">>>>>>> REPLACE"
)


class TestProtocolConformance:
    def test_isinstance_language_pod(self, tmp_path):
        assert isinstance(make_pod(tmp_path), LanguagePod)


class TestRunGreenMultiFile:
    def test_all_target_files_must_already_exist(self, tmp_path):
        s = make_multi_file_spec(tmp_path)
        s.implementation_file.parent.mkdir(parents=True, exist_ok=True)
        s.implementation_file.write_text("export function foo(): void {}\n", encoding="utf-8")
        # extra_target_files[0] (helpers.ts) never written.
        pod = make_pod(tmp_path)
        result = pod.run_green(s)
        assert not result.passed
        assert result.error.startswith("MULTI_FILE_GREEN_MISSING_FILES:")
        assert "helpers.ts" in result.error
        pod._orchestrator.pulse.assert_not_called()
        pod._worker.generate_multi_file_patch.assert_not_called()

    def test_uses_generate_multi_file_patch_not_generate_implementation(self, tmp_path):
        s = make_multi_file_spec(tmp_path)
        _write_multi_file_ts_targets(s)
        worker = make_worker()
        worker.generate_multi_file_patch.return_value = _MULTI_FILE_TS_SR_BLOCK
        pod = make_pod(tmp_path, worker=worker)
        pod.run_green(s)
        worker.generate_multi_file_patch.assert_called_once()
        worker.generate_implementation.assert_not_called()

    def test_successful_patch_is_pulsed_and_both_files_committed(self, tmp_path):
        s = make_multi_file_spec(tmp_path)
        _write_multi_file_ts_targets(s)
        worker = make_worker()
        worker.generate_multi_file_patch.return_value = _MULTI_FILE_TS_SR_BLOCK
        pod = make_pod(tmp_path, worker=worker)
        result = pod.run_green(s)
        assert result.passed
        assert "bar()" in s.implementation_file.read_text()
        assert "function bar" in s.extra_target_files[0].read_text()

    def test_pulse_receives_both_patched_files(self, tmp_path):
        s = make_multi_file_spec(tmp_path)
        _write_multi_file_ts_targets(s)
        worker = make_worker()
        worker.generate_multi_file_patch.return_value = _MULTI_FILE_TS_SR_BLOCK
        pod = make_pod(tmp_path, worker=worker)
        pod.run_green(s)
        pulsed = pod._orchestrator.pulse.call_args[0][0]
        assert "bar()" in pulsed["order.ts"]
        assert "function bar" in pulsed["helpers.ts"]

    def test_failed_pulse_commits_nothing(self, tmp_path):
        s = make_multi_file_spec(tmp_path)
        _write_multi_file_ts_targets(s)
        worker = make_worker()
        worker.generate_multi_file_patch.return_value = _MULTI_FILE_TS_SR_BLOCK
        pod = make_pod(tmp_path, worker=worker, pulse_result=PhaseResult(passed=False, output="", error="boom"))
        result = pod.run_green(s)
        assert not result.passed
        assert "bar()" not in s.implementation_file.read_text()
        assert "function bar" not in s.extra_target_files[0].read_text()

    def test_retrieved_bullet_ids_attached_to_result(self, tmp_path):
        s = make_multi_file_spec(tmp_path)
        _write_multi_file_ts_targets(s)
        worker = make_worker()
        worker.generate_multi_file_patch.return_value = _MULTI_FILE_TS_SR_BLOCK
        pod = make_pod(tmp_path, worker=worker)
        result = pod.run_green(s)
        assert result.retrieved_bullet_ids == ["b1"]

    def test_patch_that_fails_to_apply_never_reaches_the_sandbox(self, tmp_path):
        s = make_multi_file_spec(tmp_path)
        _write_multi_file_ts_targets(s)
        worker = make_worker()
        worker.generate_multi_file_patch.return_value = (
            "### FILE: order.ts\n<<<<<<< SEARCH\nnever matches this\n=======\nx\n>>>>>>> REPLACE"
        )
        pod = make_pod(tmp_path, worker=worker)
        result = pod.run_green(s)
        assert not result.passed
        assert result.error.startswith("PATCH_APPLY_FAILED:")
        pod._orchestrator.pulse.assert_not_called()

    def test_repeated_failures_escalate_with_no_whole_file_fallback(self, tmp_path):
        s = make_multi_file_spec(tmp_path)
        _write_multi_file_ts_targets(s)
        worker = make_worker()
        worker.generate_multi_file_patch.return_value = (
            "### FILE: order.ts\n<<<<<<< SEARCH\nnever matches this\n=======\nx\n>>>>>>> REPLACE"
        )
        pod = make_pod(tmp_path, worker=worker, patch_escalation_threshold=2)

        pod.run_green(s)
        pod.run_green(s)
        result = pod.run_green(s)
        assert result.error.startswith("MULTI_FILE_GREEN_ESCALATED:")
        assert worker.generate_multi_file_patch.call_count == 2  # not called a 3rd time

    def test_success_resets_the_escalation_counter(self, tmp_path):
        s = make_multi_file_spec(tmp_path)
        _write_multi_file_ts_targets(s)
        worker = make_worker()
        bad_patch = "### FILE: order.ts\n<<<<<<< SEARCH\nnever matches this\n=======\nx\n>>>>>>> REPLACE"
        worker.generate_multi_file_patch.return_value = bad_patch
        pod = make_pod(tmp_path, worker=worker, patch_escalation_threshold=2)

        pod.run_green(s)  # 1 failure
        worker.generate_multi_file_patch.return_value = _MULTI_FILE_TS_SR_BLOCK
        pod.run_green(s)  # succeeds, resets counter
        worker.generate_multi_file_patch.return_value = bad_patch
        result = pod.run_green(s)  # still under threshold again -- patch attempt, not escalated
        assert result.error.startswith("PATCH_APPLY_FAILED:")

    def test_single_file_green_unaffected_when_extra_target_files_empty(self, tmp_path):
        s = spec(tmp_path)
        worker = make_worker()
        worker.generate_implementation.return_value = "export function foo(): void {}\n"
        pod = make_pod(tmp_path, worker=worker)
        result = pod.run_green(s)
        assert result.passed
        worker.generate_multi_file_patch.assert_not_called()
        worker.generate_implementation.assert_called_once()
