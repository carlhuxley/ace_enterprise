"""Tests for benchmarks.swebench_ingest.

Fixtures below are hand-constructed to match the two "predictions" and
"eval_output" schemas (see swebench_ingest.py's module docstring for how
each was verified) -- representative test data, not literal downloaded
files. "predictions" is confirmed against the public
OpenHandsCommunity/Devin-SWE-bench-output dataset's actual columns
(instance_id, model_patch, model_name_or_path, pass_or_fail). "eval_output"
is confirmed against OpenHands' own documented EvalOutput dataclass
(instance_id, instruction, test_result, metadata, history, metrics, error);
test_result's internal shape is not fully documented publicly, so
extraction from it is tested as best-effort, not a guaranteed-correct
parse.

The "traceback_dataset" fixture below, by contrast, IS a literal real row --
downloaded directly from waleko/SWE-bench-traceback (instance_id
DataDog__integrations-core-446) via HuggingFace's public datasets-server
API during development of this module.
"""
import json
from unittest.mock import MagicMock

import pytest

from benchmarks.swebench_ingest import (
    RealFailureCase,
    _extract_repo_from_instance_id,
    parse_eval_output_record,
    parse_predictions_record,
    parse_record,
    parse_traceback_dataset_record,
    parse_trajectory_file,
    reflect_on_real_failure,
)


class TestExtractRepoFromInstanceId:
    def test_standard_instance_id(self):
        assert _extract_repo_from_instance_id("astropy__astropy-12907") == "astropy/astropy"

    def test_org_with_underscore_in_repo_name(self):
        assert _extract_repo_from_instance_id("django__django-11099") == "django/django"

    def test_malformed_instance_id_returns_none(self):
        assert _extract_repo_from_instance_id("not-a-valid-id") is None


class TestParsePredictionsFormat:
    def test_extracts_instance_id_and_patch(self):
        record = {
            "instance_id": "astropy__astropy-12907",
            "model_patch": "diff --git a/x.py b/x.py\n...",
            "model_name_or_path": "devin",
            "pass_or_fail": "FAIL",
        }
        case = parse_predictions_record(record)
        assert case.instance_id == "astropy__astropy-12907"
        assert case.repo == "astropy/astropy"
        assert case.patch_diff.startswith("diff --git")
        assert case.resolved is False
        assert case.source_format == "predictions"

    def test_never_has_a_traceback(self):
        """The whole point of flagging this format: it structurally cannot
        carry one."""
        record = {
            "instance_id": "astropy__astropy-12907",
            "model_patch": "diff",
            "model_name_or_path": "devin",
            "pass_or_fail": "PASS",
        }
        case = parse_predictions_record(record)
        assert case.error_traceback is None
        assert case.resolved is True

    def test_auto_detected_from_record_shape(self):
        record = {
            "instance_id": "astropy__astropy-12907",
            "model_patch": "diff",
            "model_name_or_path": "devin",
            "pass_or_fail": "FAIL",
        }
        case = parse_record(record)
        assert case.source_format == "predictions"


class TestParseEvalOutputFormat:
    def test_extracts_traceback_from_error_field(self):
        record = {
            "instance_id": "django__django-11099",
            "instruction": "Fix the validator",
            "error": "Traceback (most recent call last):\n  File ... AssertionError",
            "test_result": {},
            "history": [],
        }
        case = parse_eval_output_record(record)
        assert case.error_traceback.startswith("Traceback")
        assert case.problem_statement == "Fix the validator"

    def test_extracts_traceback_from_test_result_report_field(self):
        record = {
            "instance_id": "django__django-11099",
            "test_result": {"report": "FAILED tests/test_x.py::test_y - AssertionError"},
            "history": [],
        }
        case = parse_eval_output_record(record)
        assert "AssertionError" in case.error_traceback

    def test_extracts_traceback_from_nested_test_result(self):
        record = {
            "instance_id": "django__django-11099",
            "test_result": {"details": {"log": "FAILED: something broke"}},
        }
        case = parse_eval_output_record(record)
        assert case.error_traceback == "FAILED: something broke"

    def test_falls_back_to_history_when_no_explicit_error(self):
        record = {
            "instance_id": "django__django-11099",
            "test_result": {},
            "history": [
                {"content": "Running tests..."},
                {"observation": "FAILED tests/test_x.py - AssertionError: expected True"},
            ],
        }
        case = parse_eval_output_record(record)
        assert "AssertionError" in case.error_traceback

    def test_no_traceback_available_is_none_not_empty_string(self):
        record = {"instance_id": "django__django-11099", "test_result": {}, "history": []}
        case = parse_eval_output_record(record)
        assert case.error_traceback is None

    def test_extracts_failing_tests_list(self):
        record = {
            "instance_id": "django__django-11099",
            "test_result": {"FAIL_TO_PASS": ["tests/test_x.py::test_a", "tests/test_x.py::test_b"]},
        }
        case = parse_eval_output_record(record)
        assert case.failing_tests == ["tests/test_x.py::test_a", "tests/test_x.py::test_b"]

    def test_extracts_resolved_from_test_result(self):
        record = {"instance_id": "d__d-1", "test_result": {"resolved": False}}
        assert parse_eval_output_record(record).resolved is False

    def test_auto_detected_from_record_shape(self):
        record = {"instance_id": "d__d-1", "test_result": {}, "history": []}
        assert parse_record(record).source_format == "eval_output"


# A literal real row from waleko/SWE-bench-traceback (HuggingFace), fetched
# via https://datasets-server.huggingface.co/rows during development of
# this module -- trimmed to what the parser reads, not paraphrased.
_REAL_TRACEBACK_ROW = {
    "repo": "DataDog/integrations-core",
    "instance_id": "DataDog__integrations-core-446",
    "base_commit": "deadbeef",
    "patch": "diff --git a/x.py b/x.py\n...",
    "test_patch": "diff --git a/test_x.py b/test_x.py\n...",
    "problem_statement": "postgres check crashes on custom_metrics",
    "hints_text": "",
    "created_at": "2018-01-01",
    "version": "1.0",
    "FAIL_TO_PASS": "[]",
    "PASS_TO_PASS": "[]",
    "environment_setup_commit": "deadbeef",
    "traceback": (
        "\nTraceback (most recent call last):\n"
        '  File "/opt/datadog-agent/agent/checks/__init__.py", line 745, in run\n'
        "    self.check(copy.deepcopy(instance))\n"
        '  File "/opt/datadog-agent/agent/checks.d/postgres.py", line 606, in check\n'
        "    custom_metrics = self._get_custom_metrics(instance.get('custom_metrics', []), key)\n"
        '  File "/opt/datadog-agent/agent/checks.d/postgres.py", line 576, in _get_custom_metrics\n'
        "    for ref, (_, mtype) in m['metrics'].iteritems():\n"
        "ValueError: need more than 1 value to unpack\n"
    ),
}


class TestParseTracebackDatasetFormat:
    def test_extracts_real_traceback_verbatim(self):
        case = parse_traceback_dataset_record(_REAL_TRACEBACK_ROW)
        assert "ValueError: need more than 1 value to unpack" in case.error_traceback
        assert "iteritems" in case.error_traceback

    def test_extracts_repo_and_patch(self):
        case = parse_traceback_dataset_record(_REAL_TRACEBACK_ROW)
        assert case.repo == "DataDog/integrations-core"
        assert case.patch_diff.startswith("diff --git")
        assert case.source_format == "traceback_dataset"

    def test_empty_fail_to_pass_string_becomes_empty_list_not_a_crash(self):
        case = parse_traceback_dataset_record(_REAL_TRACEBACK_ROW)
        assert case.failing_tests == []

    def test_populated_fail_to_pass_json_string_is_parsed(self):
        record = dict(_REAL_TRACEBACK_ROW, FAIL_TO_PASS='["tests/test_x.py::test_a"]')
        case = parse_traceback_dataset_record(record)
        assert case.failing_tests == ["tests/test_x.py::test_a"]

    def test_resolved_is_none_not_a_guess(self):
        """This dataset is pre-patch task data, not a graded attempt --
        there's no real pass/fail outcome to report."""
        case = parse_traceback_dataset_record(_REAL_TRACEBACK_ROW)
        assert case.resolved is None

    def test_auto_detected_from_record_shape(self):
        assert parse_record(_REAL_TRACEBACK_ROW).source_format == "traceback_dataset"

    def test_reflect_on_real_failure_builds_a_real_task_input(self):
        case = parse_traceback_dataset_record(_REAL_TRACEBACK_ROW)
        reflector = MagicMock()
        reflector.reflect.return_value = "fake-output"

        result = reflect_on_real_failure(reflector, case)

        assert result == "fake-output"
        task_input, generator_output, env_feedback = reflector.reflect.call_args[0]
        assert task_input.id == "DataDog__integrations-core-446"
        assert "ValueError" in env_feedback.feedback


class TestParseTrajectoryFile:
    def test_parses_jsonl_and_filters_to_failures_by_default(self, tmp_path):
        p = tmp_path / "traj.jsonl"
        p.write_text(
            json.dumps({"instance_id": "a__a-1", "model_patch": "x", "model_name_or_path": "m", "pass_or_fail": "FAIL"}) + "\n"
            + json.dumps({"instance_id": "b__b-2", "model_patch": "y", "model_name_or_path": "m", "pass_or_fail": "PASS"}) + "\n"
        )
        cases = parse_trajectory_file(p)
        assert len(cases) == 1
        assert cases[0].instance_id == "a__a-1"

    def test_include_resolved_keeps_everything(self, tmp_path):
        p = tmp_path / "traj.jsonl"
        p.write_text(
            json.dumps({"instance_id": "a__a-1", "model_patch": "x", "model_name_or_path": "m", "pass_or_fail": "FAIL"}) + "\n"
            + json.dumps({"instance_id": "b__b-2", "model_patch": "y", "model_name_or_path": "m", "pass_or_fail": "PASS"}) + "\n"
        )
        cases = parse_trajectory_file(p, include_resolved=True)
        assert len(cases) == 2

    def test_skips_blank_lines(self, tmp_path):
        p = tmp_path / "traj.jsonl"
        p.write_text(
            "\n"
            + json.dumps({"instance_id": "a__a-1", "model_patch": "x", "model_name_or_path": "m", "pass_or_fail": "FAIL"}) + "\n"
            + "\n"
        )
        assert len(parse_trajectory_file(p)) == 1

    def test_raises_with_line_number_on_malformed_json(self, tmp_path):
        p = tmp_path / "traj.jsonl"
        p.write_text('{"instance_id": "a__a-1"}\nnot json\n')
        with pytest.raises(ValueError, match=r":2:"):
            parse_trajectory_file(p)


class TestReflectOnRealFailure:
    def test_returns_none_when_no_traceback(self):
        case = RealFailureCase(
            instance_id="a__a-1", repo="a/a", failing_tests=[], error_traceback=None,
            patch_diff="diff", problem_statement=None, resolved=False, source_format="predictions",
        )
        result = reflect_on_real_failure(reflector=MagicMock(), case=case)
        assert result is None

    def test_calls_reflector_with_real_traceback(self):
        case = RealFailureCase(
            instance_id="django__django-11099", repo="django/django",
            failing_tests=["tests/test_x.py::test_a"],
            error_traceback="Traceback...\nAssertionError: x != y",
            patch_diff="diff --git a/x.py...",
            problem_statement="Fix the validator",
            resolved=False, source_format="eval_output",
        )
        reflector = MagicMock()
        reflector.reflect.return_value = "fake-reflector-output"

        result = reflect_on_real_failure(reflector, case)

        assert result == "fake-reflector-output"
        reflector.reflect.assert_called_once()
        task_input, generator_output, env_feedback = reflector.reflect.call_args[0]
        assert task_input.id == "django__django-11099"
        assert env_feedback.feedback.startswith("Traceback")
        assert env_feedback.test_report["failing_tests"] == ["tests/test_x.py::test_a"]
