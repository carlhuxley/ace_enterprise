"""Tests for build_pod_kwargs / build_all_pod_kwargs (sandboxed pod wiring)."""
from unittest.mock import MagicMock

import pytest

from src.agents.go_language_pod import GoLanguagePod
from src.agents.podman_orchestrator import PodmanOrchestrator
from src.agents.podman_runner import PodmanRunner
from src.agents.python_language_pod import PythonLanguagePod
from src.agents.typescript_language_pod import TypeScriptLanguagePod
from src.agents.typescript_runner import TypeScriptRunner
from src.agents.go_runner import GoRunner
from src.agents.polyglot_pod_builder import build_all_pod_kwargs, build_pod_kwargs
from src.agents.polyglot_tdd_runner import PodFactory


class TestBuildPodKwargs:
    def test_python_kwargs_build_a_working_python_pod(self, tmp_path):
        kwargs = build_pod_kwargs("python", tmp_path, llm_client=MagicMock())
        assert isinstance(kwargs["orchestrator"], PodmanOrchestrator)
        assert isinstance(kwargs["orchestrator"]._runner, PodmanRunner)
        assert kwargs["project_root"] == tmp_path
        pod = PodFactory.create("python", **kwargs)
        assert isinstance(pod, PythonLanguagePod)

    def test_typescript_kwargs_build_a_working_typescript_pod(self, tmp_path):
        kwargs = build_pod_kwargs("typescript", tmp_path, llm_client=MagicMock())
        assert isinstance(kwargs["orchestrator"]._runner, TypeScriptRunner)
        pod = PodFactory.create("typescript", **kwargs)
        assert isinstance(pod, TypeScriptLanguagePod)

    def test_go_kwargs_build_a_working_go_pod(self, tmp_path):
        kwargs = build_pod_kwargs("go", tmp_path, llm_client=MagicMock())
        assert isinstance(kwargs["orchestrator"]._runner, GoRunner)
        pod = PodFactory.create("go", **kwargs)
        assert isinstance(pod, GoLanguagePod)

    def test_unsupported_language_raises(self, tmp_path):
        with pytest.raises(ValueError, match="ruby"):
            build_pod_kwargs("ruby", tmp_path, llm_client=MagicMock())

    def test_each_language_gets_its_own_sandbox_image(self, tmp_path):
        # The whole point of per-language runners: different container images,
        # not one runner reused (and silently misconfigured) across languages.
        py_runner = build_pod_kwargs("python", tmp_path, MagicMock())["orchestrator"]._runner
        ts_runner = build_pod_kwargs("typescript", tmp_path, MagicMock())["orchestrator"]._runner
        go_runner = build_pod_kwargs("go", tmp_path, MagicMock())["orchestrator"]._runner
        assert py_runner._image != ts_runner._image != go_runner._image


class TestBuildAllPodKwargs:
    def test_builds_kwargs_for_every_requested_language(self, tmp_path):
        all_kwargs = build_all_pod_kwargs(
            ["python", "typescript", "go"], tmp_path, llm_client=MagicMock()
        )
        assert set(all_kwargs.keys()) == {"python", "typescript", "go"}
        for lang, kwargs in all_kwargs.items():
            pod = PodFactory.create(lang, **kwargs)
            assert pod is not None
