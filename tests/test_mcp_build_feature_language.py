"""Tests for the sandboxed, multi-language build_feature MCP tool.

build_feature drives PolyglotTDDRunner/PodFactory through the Podman-backed
language pods -- these tests replace PolyglotTDDRunner with a stub so no real
podman/container/LLM calls happen, and assert on the wiring: which language
maps to which file convention, that PodFactory receives working per-language
kwargs (via polyglot_pod_builder), and that the LLM client defaults to the
no-API-key ClaudeCliClient (this tool is meant to be driven from a local
Claude Code session over MCP).
"""
from unittest.mock import MagicMock, patch

import pytest

from mcp_server.tools import ACETools, _pod_file_paths, _slugify
from src.agents.language_pod import PhaseResult
from src.agents.polyglot_tdd_runner import LanguageRunResult, PolyglotRunResult
from src.analytics.token_efficiency import EfficiencyReport
from src.audit.local_client import LocalAuditClient


def _fake_run_result(language: str, green_passed: bool = True, refactor_passed: bool = True):
    return LanguageRunResult(
        language=language,
        red=PhaseResult(passed=False, output="", error="AssertionError (expected RED)"),
        green=PhaseResult(passed=green_passed, output="ok", error=None if green_passed else "boom"),
        refactor=PhaseResult(passed=refactor_passed, output="ok"),
        cycles_to_green=1,
    )


def _fake_polyglot_result(language: str, **kw) -> PolyglotRunResult:
    return PolyglotRunResult(
        language_results={language: _fake_run_result(language, **kw)},
        efficiency_report=EfficiencyReport(),
    )


@pytest.fixture
def tools(tmp_path):
    t = ACETools(playbook_id="pb1")
    t._audit = LocalAuditClient(database_url=f"sqlite:///{tmp_path}/audit.db")
    return t


@pytest.fixture
def stub_runner_cls():
    """Patch PolyglotTDDRunner so build_feature never touches real containers."""
    with patch("src.agents.polyglot_tdd_runner.PolyglotTDDRunner") as cls:
        yield cls


@pytest.fixture
def stub_pod_kwargs():
    with patch("src.agents.polyglot_pod_builder.build_pod_kwargs", return_value={}) as fn:
        yield fn


class TestFileConventions:
    def test_python_paths(self, tmp_path):
        test_file, impl_file = _pod_file_paths("python", "user_auth", tmp_path / "src", tmp_path / "tests")
        assert test_file.name == "test_user_auth.py"
        assert impl_file.name == "user_auth.py"

    def test_typescript_paths(self, tmp_path):
        test_file, impl_file = _pod_file_paths("typescript", "user_auth", tmp_path / "src", tmp_path / "tests")
        assert test_file.name == "user_auth.test.ts"
        assert impl_file.name == "user_auth.ts"

    def test_go_paths(self, tmp_path):
        test_file, impl_file = _pod_file_paths("go", "user_auth", tmp_path / "src", tmp_path / "tests")
        assert test_file.name == "user_auth_test.go"
        assert impl_file.name == "user_auth.go"

    def test_unsupported_language_raises(self, tmp_path):
        with pytest.raises(ValueError):
            _pod_file_paths("ruby", "x", tmp_path, tmp_path)


class TestSlugify:
    def test_derives_readable_module_name(self):
        assert _slugify("User logs in with a valid JWT") == "user_logs_in_with_a_valid"

    def test_empty_text_falls_back_to_feature(self):
        assert _slugify("!!!") == "feature"


class TestBuildFeatureLanguageRouting:
    def test_defaults_to_python(self, tools, stub_runner_cls, stub_pod_kwargs, tmp_path):
        stub_runner_cls.return_value.run.return_value = _fake_polyglot_result("python")

        result = tools._handle_build_feature({
            "feature": "User logs in with a valid token",
            "project_path": str(tmp_path),
        })

        assert result["success"] is True
        assert result["sandboxed"] is True
        assert result["language"] == "python"
        assert result["test_file"].endswith("test_user_logs_in_with_a_valid.py")
        assert result["implementation_file"].endswith("user_logs_in_with_a_valid.py")
        # languages=["python"] was requested from the (stubbed) runner
        _, run_kwargs = stub_runner_cls.return_value.run.call_args
        assert run_kwargs["languages"] == ["python"]

    def test_typescript_language_selects_ts_pod_and_paths(self, tools, stub_runner_cls, stub_pod_kwargs, tmp_path):
        stub_runner_cls.return_value.run.return_value = _fake_polyglot_result("typescript")

        result = tools._handle_build_feature({
            "feature": "User logs in with a valid token",
            "language": "typescript",
            "name": "login",
            "project_path": str(tmp_path),
        })

        assert result["success"] is True
        assert result["language"] == "typescript"
        assert result["test_file"].endswith("login.test.ts")
        assert result["implementation_file"].endswith("login.ts")

    def test_go_language_selects_go_pod_and_paths(self, tools, stub_runner_cls, stub_pod_kwargs, tmp_path):
        stub_runner_cls.return_value.run.return_value = _fake_polyglot_result("go")

        result = tools._handle_build_feature({
            "feature": "User logs in with a valid token",
            "language": "go",
            "name": "login",
            "project_path": str(tmp_path),
        })

        assert result["success"] is True
        assert result["language"] == "go"
        assert result["test_file"].endswith("login_test.go")
        assert result["implementation_file"].endswith("login.go")

    def test_unsupported_language_returns_error_without_running(self, tools, stub_runner_cls, tmp_path):
        result = tools._handle_build_feature({
            "feature": "x",
            "language": "ruby",
            "project_path": str(tmp_path),
        })
        assert result["success"] is False
        assert "ruby" in result["error"]
        stub_runner_cls.return_value.run.assert_not_called()

    def test_missing_feature_and_feature_file_returns_error(self, tools, stub_runner_cls, tmp_path):
        result = tools._handle_build_feature({"project_path": str(tmp_path)})
        assert result["success"] is False
        assert "feature" in result["error"].lower()

    def test_green_failure_is_reported_as_unsuccessful(self, tools, stub_runner_cls, stub_pod_kwargs, tmp_path):
        stub_runner_cls.return_value.run.return_value = _fake_polyglot_result(
            "python", green_passed=False
        )
        result = tools._handle_build_feature({
            "feature": "User logs in",
            "project_path": str(tmp_path),
        })
        assert result["success"] is False
        assert result["green_passed"] is False

    def test_feature_file_is_parsed_via_gherkin_bridge(self, tools, stub_runner_cls, stub_pod_kwargs, tmp_path):
        stub_runner_cls.return_value.run.return_value = _fake_polyglot_result("python")
        feature_path = tmp_path / "login.feature"
        feature_path.write_text(
            "Feature: User login\n\n  Scenario: valid credentials\n"
            "    Given a user\n    When they log in\n    Then they see the dashboard\n"
        )

        result = tools._handle_build_feature({
            "feature_file": str(feature_path),
            "project_path": str(tmp_path),
        })

        assert result["success"] is True
        assert "User login" in result["requirement"]


class TestParityWithSandboxedCLIEngine:
    """build_feature should wire the same audit/redundancy/context-map
    extensions as ace tdd's build_agent() -- not a parallel, drifted copy.
    """

    def test_audit_client_passed_to_polyglot_runner(self, tools, stub_runner_cls, stub_pod_kwargs, tmp_path):
        stub_runner_cls.return_value.run.return_value = _fake_polyglot_result("python")
        tools._handle_build_feature({
            "feature": "User logs in", "project_path": str(tmp_path),
        })
        _, kwargs = stub_runner_cls.call_args
        assert kwargs["audit_client"] is tools._audit

    def test_team_id_passed_to_polyglot_runner(self, tools, stub_runner_cls, stub_pod_kwargs, tmp_path):
        stub_runner_cls.return_value.run.return_value = _fake_polyglot_result("python")
        tools._handle_build_feature({
            "feature": "User logs in", "project_path": str(tmp_path), "team_id": "payments",
        })
        _, kwargs = stub_runner_cls.call_args
        assert kwargs["team_id"] == "payments"

    def test_team_id_defaults_to_none(self, tools, stub_runner_cls, stub_pod_kwargs, tmp_path):
        stub_runner_cls.return_value.run.return_value = _fake_polyglot_result("python")
        tools._handle_build_feature({
            "feature": "User logs in", "project_path": str(tmp_path),
        })
        _, kwargs = stub_runner_cls.call_args
        assert kwargs["team_id"] is None

    def test_redundancy_checker_passed_to_polyglot_runner(self, tools, stub_runner_cls, stub_pod_kwargs, tmp_path):
        from src.agents.redundancy_checker import RedundancyPreChecker

        stub_runner_cls.return_value.run.return_value = _fake_polyglot_result("python")
        tools._handle_build_feature({
            "feature": "User logs in", "project_path": str(tmp_path),
        })
        _, kwargs = stub_runner_cls.call_args
        assert isinstance(kwargs["redundancy_checker"], RedundancyPreChecker)

    def test_playbook_id_passed_to_polyglot_runner(self, tools, stub_runner_cls, stub_pod_kwargs, tmp_path):
        stub_runner_cls.return_value.run.return_value = _fake_polyglot_result("python")
        tools._handle_build_feature({
            "feature": "User logs in", "project_path": str(tmp_path),
        })
        _, kwargs = stub_runner_cls.call_args
        assert kwargs["playbook_id"] == "pb1"

    def test_build_pod_kwargs_receives_resolved_src_dir(self, tools, stub_runner_cls, tmp_path):
        stub_runner_cls.return_value.run.return_value = _fake_polyglot_result("python")
        with patch("src.agents.polyglot_pod_builder.build_pod_kwargs", return_value={}) as build:
            tools._handle_build_feature({
                "feature": "User logs in",
                "project_path": str(tmp_path),
                "src_dir": "lib",
            })
        _, kwargs = build.call_args
        assert kwargs["src_dir"] == tmp_path / "lib"


class TestPolyglotPodBuilderContextMap:
    """build_pod_kwargs (used by both ace tdd and build_feature) wires a
    ContextMap into the Python worker, scanning src_dir specifically.
    """

    def test_python_worker_gets_context_map_from_src_dir(self, tmp_path):
        from unittest.mock import MagicMock
        from src.agents.polyglot_tdd_runner import PodFactory
        from src.agents.polyglot_pod_builder import build_pod_kwargs

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

        kwargs = build_pod_kwargs("python", tmp_path, MagicMock(), src_dir=src_dir)
        pod = PodFactory.create("python", **kwargs)
        names = [sig.name for sig in pod._worker._context_map.all_signatures()]
        assert "add" in names

    def test_defaults_to_project_root_when_src_dir_omitted(self, tmp_path):
        from unittest.mock import MagicMock
        from src.agents.polyglot_pod_builder import build_pod_kwargs

        (tmp_path / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")
        kwargs = build_pod_kwargs("python", tmp_path, MagicMock())
        names = [sig.name for sig in kwargs["worker"]._context_map.all_signatures()]
        assert "add" in names


class TestResolveLLMClient:
    def test_defaults_to_claude_cli_no_api_key(self, tools):
        from src.utils.claude_cli_client import ClaudeCliClient
        client = tools._resolve_llm_client({})
        assert isinstance(client, ClaudeCliClient)

    def test_explicit_model_uses_llm_client(self, tools):
        from src.utils.llm_client import LLMClient
        client = tools._resolve_llm_client({"model": "qwen/qwen3-coder:free"})
        assert isinstance(client, LLMClient)
        assert client.provider == "openrouter"
