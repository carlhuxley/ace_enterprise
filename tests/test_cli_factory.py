"""Tests for src/cli/factory.py -- the sandboxed engine behind `ace tdd`.

build_agent() used to wire AutonomousTDDAgent (host subprocess pytest, direct
writes to the project's real files). It now wires IterativeTDDRunner against
a PythonLanguagePod/PodmanOrchestrator, matching bootstrap/orchestrate.py's
synthesis loop. These tests check the wiring itself; PodmanRunner/LLMClient
are never exercised for real (no podman/API calls needed to run this file).
"""
from unittest.mock import MagicMock, patch

import pytest

from src.agents.iterative_tdd_runner import IterativeTDDRunner
from src.agents.podman_orchestrator import PodmanOrchestrator
from src.agents.podman_runner import PodmanRunner
from src.agents.python_language_pod import PythonLanguagePod
from src.cli.config import ProjectConfig
from src.cli.factory import TDDRunHandle, build_agent


@pytest.fixture
def config(tmp_path):
    src_dir = tmp_path / "src"
    test_dir = tmp_path / "tests"
    src_dir.mkdir()
    test_dir.mkdir()
    return ProjectConfig(
        project_root=tmp_path,
        test_dir=test_dir,
        src_dir=src_dir,
        playbook_id="test-project",
        max_iterations=5,
    )


class TestBuildAgentWiring:
    def test_returns_tdd_run_handle(self, config):
        handle = build_agent(config)
        assert isinstance(handle, TDDRunHandle)
        assert isinstance(handle.runner, IterativeTDDRunner)

    def test_runner_is_backed_by_a_sandboxed_python_pod(self, config):
        handle = build_agent(config)
        assert isinstance(handle.runner._pod, PythonLanguagePod)
        assert isinstance(handle.runner._pod._orchestrator, PodmanOrchestrator)
        assert isinstance(handle.runner._pod._orchestrator._runner, PodmanRunner)

    def test_handle_dirs_match_config(self, config):
        handle = build_agent(config)
        assert handle.test_dir == config.test_dir
        assert handle.src_dir == config.src_dir

    def test_learn_enabled_by_default_wires_reflector_and_curator(self, config):
        handle = build_agent(config)
        kwargs = handle.runner._runner_kwargs
        assert kwargs["reflector"] is not None
        assert kwargs["curator"] is not None

    def test_skip_learn_omits_reflector_and_curator(self, config):
        handle = build_agent(config, skip_learn=True)
        kwargs = handle.runner._runner_kwargs
        assert kwargs["reflector"] is None
        assert kwargs["curator"] is None

    def test_max_iterations_forwarded(self, config):
        handle = build_agent(config)
        assert handle.runner._max_iterations == config.max_iterations

    def test_team_id_forwarded_from_config(self, config):
        config.team_id = "payments"
        handle = build_agent(config)
        assert handle.runner._runner_kwargs["team_id"] == "payments"

    def test_team_id_defaults_to_none(self, config):
        handle = build_agent(config)
        assert handle.runner._runner_kwargs["team_id"] is None

    def test_no_routing_without_candidate_models(self, config):
        handle = build_agent(config)
        assert handle.routing is None

    def test_model_ref_sets_the_runner_model_id(self, config):
        handle = build_agent(config, model_ref="openrouter/qwen/qwen3-coder")
        assert handle.runner._runner_kwargs["model_id"] == "openrouter/qwen/qwen3-coder"

    def test_model_ref_beats_candidate_models_routing(self, config):
        config.candidate_models = ["ollama/a", "ollama/b"]
        with patch("src.cli.factory.route_model") as route:
            handle = build_agent(config, model_ref="anthropic/claude-sonnet-4-5")
        route.assert_not_called()
        assert handle.routing is None
        assert handle.runner._runner_kwargs["model_id"] == "anthropic/claude-sonnet-4-5"

    def test_model_ref_with_bad_provider_raises(self, config):
        with pytest.raises(ValueError, match="unknown provider"):
            build_agent(config, model_ref="qwen/qwen3-coder")

    def test_model_ref_claude_cli_uses_the_local_cli_backend(self, config):
        from src.utils.claude_cli_client import ClaudeCliClient
        handle = build_agent(config, model_ref="claude-cli")
        assert isinstance(handle.runner._pod._worker.llm_client, ClaudeCliClient)

    def test_model_ref_claude_cli_with_a_model_picks_it(self, config):
        handle = build_agent(config, model_ref="claude-cli/haiku")
        assert handle.runner._pod._worker.llm_client._model == "haiku"
        assert handle.runner._runner_kwargs["model_id"] == "claude-cli/claude-cli:haiku"

    def test_single_candidate_model_does_not_route(self, config):
        config.candidate_models = ["openrouter/qwen/q1"]
        handle = build_agent(config)
        assert handle.routing is None

    def test_candidate_models_route_and_select_the_model(self, config):
        config.candidate_models = ["openrouter/deepseek/deepseek-v3", "ollama/qwen2.5-coder:7b"]
        fake = MagicMock()
        fake.selected_model = "ollama/qwen2.5-coder:7b"
        fake.to_payload.return_value = {"selected_model": "ollama/qwen2.5-coder:7b"}
        with patch("src.cli.factory.route_model", return_value=fake) as route:
            handle = build_agent(config)
        route.assert_called_once()
        assert handle.routing is fake
        # The selected "<provider>/<model>" ref is what the runner records as model_id.
        assert handle.runner._runner_kwargs["model_id"] == "ollama/qwen2.5-coder:7b"

    def test_routing_decision_is_audited(self, config):
        config.candidate_models = ["openrouter/deepseek/deepseek-v3", "ollama/qwen2.5-coder:7b"]
        fake = MagicMock()
        fake.selected_model = "openrouter/deepseek/deepseek-v3"
        fake.to_payload.return_value = {"selected_model": "openrouter/deepseek/deepseek-v3"}
        with patch("src.cli.factory.route_model", return_value=fake), \
             patch("src.audit.local_client.LocalAuditClient.emit_simple") as emit:
            build_agent(config)
        event_types = [c.kwargs.get("event_type") for c in emit.call_args_list]
        from src.audit.schemas import AuditEventType
        assert AuditEventType.ROUTING_DECISION in event_types

    def test_audit_client_wired(self, config):
        # Parity with AutonomousTDDAgent, which emitted audit events natively.
        from src.audit.local_client import LocalAuditClient
        handle = build_agent(config)
        assert isinstance(handle.runner._runner_kwargs["audit_client"], LocalAuditClient)

    def test_redundancy_checker_wired(self, config):
        from src.agents.redundancy_checker import RedundancyPreChecker
        handle = build_agent(config)
        assert isinstance(handle.runner._redundancy_checker, RedundancyPreChecker)

    def test_context_map_wired_into_worker(self, config):
        from src.utils.context_map import ContextMap
        handle = build_agent(config)
        assert isinstance(handle.runner._pod._worker._context_map, ContextMap)

    def test_context_map_includes_existing_src_files(self, config):
        (config.src_dir / "calculator.py").write_text(
            "def add(a: int, b: int) -> int:\n    return a + b\n"
        )
        handle = build_agent(config)
        cm = handle.runner._pod._worker._context_map
        names = [sig.name for sig in cm.all_signatures()]
        assert "add" in names

    def test_stop_stops_the_orchestrator(self, config):
        handle = build_agent(config)
        handle.orchestrator = MagicMock()
        handle.stop()
        handle.orchestrator.stop.assert_called_once()


class TestBuildFromFeature:
    def _handle_with_stub_runner(self, config):
        stub_runner = MagicMock()
        stub_runner.run.return_value = "fake-result"
        return TDDRunHandle(
            runner=stub_runner,
            orchestrator=MagicMock(),
            test_dir=config.test_dir,
            src_dir=config.src_dir,
        ), stub_runner

    def test_pins_file_paths_from_feature_stem(self, config):
        feature = config.project_root / "login.feature"
        feature.write_text("Feature: User login\n\n  Scenario: ok\n    Given a user\n")
        handle, stub_runner = self._handle_with_stub_runner(config)

        result = handle.build_from_feature(feature)

        assert result == "fake-result"
        _, kwargs = stub_runner.run.call_args
        assert kwargs["test_file"] == config.test_dir / "test_login.py"
        assert kwargs["impl_file"] == config.src_dir / "login.py"

    def test_default_requirement_derived_from_feature_file(self, config):
        feature = config.project_root / "login.feature"
        feature.write_text(
            "Feature: User login\n\n  Scenario: valid creds\n    Given a user\n"
        )
        handle, stub_runner = self._handle_with_stub_runner(config)

        handle.build_from_feature(feature)

        _, kwargs = stub_runner.run.call_args
        assert "User login" in kwargs["requirement"]

    def test_explicit_requirement_overrides_derived_one(self, config):
        feature = config.project_root / "login.feature"
        feature.write_text("Feature: User login\n\n  Scenario: ok\n    Given a user\n")
        handle, stub_runner = self._handle_with_stub_runner(config)

        handle.build_from_feature(feature, requirement="custom override text")

        _, kwargs = stub_runner.run.call_args
        assert kwargs["requirement"] == "custom override text"

    def test_file_paths_for_matches_build_from_feature_pinning(self, config):
        feature = config.project_root / "login.feature"
        handle, _ = self._handle_with_stub_runner(config)
        test_file, impl_file = handle.file_paths_for(feature)
        assert test_file == config.test_dir / "test_login.py"
        assert impl_file == config.src_dir / "login.py"
