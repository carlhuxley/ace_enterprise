"""Tests for src/agents/sandbox_image_builder.py (#53). subprocess is mocked
throughout -- no real podman build here (that's exercised live via
validate_module's existing skip_no_podman tests once wired up)."""

from unittest.mock import MagicMock, patch

import pytest

from src.agents.sandbox_image_builder import SandboxImageBuildError, ensure_image_with_packages


def test_empty_packages_returns_base_image_unchanged():
    assert ensure_image_with_packages(frozenset()) == "localhost/ace-harness:latest"


def test_invalid_package_name_is_rejected_before_any_subprocess_call():
    with patch("subprocess.run") as run:
        with pytest.raises(SandboxImageBuildError, match="not a valid PyPI package name"):
            ensure_image_with_packages(frozenset({"flask; rm -rf /"}))
        run.assert_not_called()


def test_cached_image_skips_build():
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)
        tag = ensure_image_with_packages(frozenset({"flask"}))
        assert tag.startswith("localhost/ace-harness-deps:")
        run.assert_called_once()  # only the `podman image exists` check
        assert run.call_args[0][0][:3] == ["podman", "image", "exists"]


def test_successful_build_returns_new_tag():
    exists_result = MagicMock(returncode=1)  # cache miss
    build_result = MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", side_effect=[exists_result, build_result]) as run:
        tag = ensure_image_with_packages(frozenset({"flask"}))
    assert tag.startswith("localhost/ace-harness-deps:")
    assert run.call_count == 2
    build_call = run.call_args_list[1][0][0]
    assert build_call[:2] == ["podman", "build"]
    assert "-t" in build_call and tag in build_call


def test_failed_build_raises_with_stderr_tail():
    exists_result = MagicMock(returncode=1)
    build_result = MagicMock(returncode=1, stdout="", stderr="ERROR: No matching distribution")
    with patch("subprocess.run", side_effect=[exists_result, build_result]):
        with pytest.raises(SandboxImageBuildError, match="No matching distribution"):
            ensure_image_with_packages(frozenset({"not-a-real-package-xyz"}))


def test_same_package_set_produces_a_stable_tag_regardless_of_order():
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)
        tag_a = ensure_image_with_packages(frozenset({"flask", "gradio"}))
        tag_b = ensure_image_with_packages(frozenset({"gradio", "flask"}))
    assert tag_a == tag_b


def test_different_package_sets_produce_different_tags():
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)
        tag_a = ensure_image_with_packages(frozenset({"flask"}))
        tag_b = ensure_image_with_packages(frozenset({"gradio"}))
    assert tag_a != tag_b
