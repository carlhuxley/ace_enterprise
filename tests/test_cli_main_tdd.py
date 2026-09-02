"""Tests for `ace tdd` (src/cli/main.py::cmd_tdd).

build_agent() is patched throughout -- these tests check cmd_tdd's own
control flow (path resolution, error handling, handle lifecycle), not the
sandboxed engine itself (covered by tests/test_cli_factory.py).
"""
import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.cli.main import cmd_tdd


def _args(**overrides):
    defaults = {
        "project": Path("."),
        "feature": None,
        "requirement": None,
        "model": None,
        "playbook_id": None,
        "max_iterations": None,
        "no_learn": False,
        "keep_going": False,
        "verbose": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "features").mkdir()
    feature = tmp_path / "features" / "login.feature"
    feature.write_text("Feature: User login\n\n  Scenario: ok\n    Given a user\n")
    return tmp_path


def _stub_handle(success=True, iterations=2):
    handle = MagicMock()
    handle.build_from_feature.return_value = MagicMock(success=success, iterations=iterations)
    handle.file_paths_for.return_value = (Path("tests/test_login.py"), Path("src/login.py"))
    return handle


class TestErrorPaths:
    def test_missing_project_dir_returns_1(self, tmp_path, capsys):
        rc = cmd_tdd(_args(project=tmp_path / "does_not_exist"))
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_no_feature_files_returns_1(self, tmp_path, capsys):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        rc = cmd_tdd(_args(project=tmp_path))
        assert rc == 1
        assert "no .feature files found" in capsys.readouterr().err

    def test_explicit_missing_feature_file_returns_1(self, project, capsys):
        rc = cmd_tdd(_args(project=project, feature=Path("nope.feature")))
        assert rc == 1
        assert "feature file not found" in capsys.readouterr().err


class TestSuccessPath:
    def test_builds_from_discovered_feature(self, project):
        with patch("src.cli.factory.build_agent", return_value=_stub_handle()) as build_agent:
            rc = cmd_tdd(_args(project=project))
        assert rc == 0
        build_agent.assert_called_once()
        _, kwargs = build_agent.call_args
        assert kwargs["skip_learn"] is False

    def test_no_learn_flag_forwarded(self, project):
        with patch("src.cli.factory.build_agent", return_value=_stub_handle()) as build_agent:
            cmd_tdd(_args(project=project, no_learn=True))
        _, kwargs = build_agent.call_args
        assert kwargs["skip_learn"] is True

    def test_requirement_override_forwarded_to_handle(self, project):
        handle = _stub_handle()
        with patch("src.cli.factory.build_agent", return_value=handle):
            cmd_tdd(_args(project=project, requirement="custom text"))
        _, kwargs = handle.build_from_feature.call_args
        assert kwargs["requirement"] == "custom text"

    def test_incomplete_result_returns_1(self, project):
        with patch("src.cli.factory.build_agent", return_value=_stub_handle(success=False)):
            rc = cmd_tdd(_args(project=project))
        assert rc == 1

    def test_handle_is_stopped_after_success(self, project):
        handle = _stub_handle()
        with patch("src.cli.factory.build_agent", return_value=handle):
            cmd_tdd(_args(project=project))
        handle.stop.assert_called_once()

    def test_handle_is_stopped_even_if_build_raises(self, project):
        handle = _stub_handle()
        handle.build_from_feature.side_effect = RuntimeError("container boom")
        with patch("src.cli.factory.build_agent", return_value=handle):
            with pytest.raises(RuntimeError):
                cmd_tdd(_args(project=project))
        handle.stop.assert_called_once()

    def test_explicit_feature_path_relative_to_project(self, project):
        with patch("src.cli.factory.build_agent", return_value=_stub_handle()) as build_agent:
            rc = cmd_tdd(_args(project=project, feature=Path("features/login.feature")))
        assert rc == 0
        build_agent.assert_called_once()


class TestModelOverride:
    def test_model_ref_forwarded_to_build_agent(self, project):
        with patch("src.cli.factory.build_agent", return_value=_stub_handle()) as build_agent:
            rc = cmd_tdd(_args(project=project, model="openrouter/qwen/qwen3-coder"))
        assert rc == 0
        _, kwargs = build_agent.call_args
        assert kwargs["model_ref"] == "openrouter/qwen/qwen3-coder"

    def test_no_model_flag_passes_none(self, project):
        with patch("src.cli.factory.build_agent", return_value=_stub_handle()) as build_agent:
            cmd_tdd(_args(project=project))
        _, kwargs = build_agent.call_args
        assert kwargs["model_ref"] is None

    def test_bad_model_ref_is_rejected_before_building(self, project, capsys):
        with patch("src.cli.factory.build_agent") as build_agent:
            rc = cmd_tdd(_args(project=project, model="qwen/qwen3-coder"))  # missing provider
        assert rc == 1
        build_agent.assert_not_called()
        assert "unknown provider" in capsys.readouterr().err

    def test_model_ref_without_slash_is_rejected(self, project, capsys):
        with patch("src.cli.factory.build_agent") as build_agent:
            rc = cmd_tdd(_args(project=project, model="justqwen"))
        assert rc == 1
        build_agent.assert_not_called()
        assert "<provider>/<model>" in capsys.readouterr().err


class TestMultiFeature:
    @pytest.fixture
    def multi_project(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        feats = tmp_path / "features"
        feats.mkdir()
        (feats / "db.feature").write_text("Feature: DB\n\n  Scenario: s\n    Given x\n")
        (feats / "auth.feature").write_text(
            "@depends_on(db)\nFeature: Auth\n\n  Scenario: s\n    Given x\n"
        )
        (feats / "api.feature").write_text(
            "@depends_on(auth, db)\nFeature: API\n\n  Scenario: s\n    Given x\n"
        )
        return tmp_path

    def _paths_for(self, feature_path):
        stem = Path(feature_path).stem
        return (Path(f"tests/test_{stem}.py"), Path(f"src/{stem}.py"))

    def test_builds_every_feature_in_dependency_order(self, multi_project):
        handle = _stub_handle()
        handle.file_paths_for.side_effect = self._paths_for
        built = []
        handle.build_from_feature.side_effect = lambda fp, requirement=None: (
            built.append(Path(fp).stem) or MagicMock(success=True, iterations=1)
        )
        with patch("src.cli.factory.build_agent", return_value=handle):
            rc = cmd_tdd(_args(project=multi_project))
        assert rc == 0
        assert built == ["db", "auth", "api"]

    def test_lexical_order_when_no_depends_on_tags(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        feats = tmp_path / "features"
        feats.mkdir()
        for name in ("charlie", "alpha", "bravo"):
            (feats / f"{name}.feature").write_text(
                f"Feature: {name}\n\n  Scenario: s\n    Given x\n"
            )
        handle = _stub_handle()
        handle.file_paths_for.side_effect = self._paths_for
        built = []
        handle.build_from_feature.side_effect = lambda fp, requirement=None: (
            built.append(Path(fp).stem) or MagicMock(success=True, iterations=1)
        )
        with patch("src.cli.factory.build_agent", return_value=handle):
            cmd_tdd(_args(project=tmp_path))
        assert built == ["alpha", "bravo", "charlie"]

    def test_stops_at_first_failure_by_default(self, multi_project):
        handle = _stub_handle()
        handle.file_paths_for.side_effect = self._paths_for
        built = []

        def build(fp, requirement=None):
            stem = Path(fp).stem
            built.append(stem)
            return MagicMock(success=(stem != "db"), iterations=1)

        handle.build_from_feature.side_effect = build
        with patch("src.cli.factory.build_agent", return_value=handle):
            rc = cmd_tdd(_args(project=multi_project))
        assert rc == 1
        assert built == ["db"]  # auth/api never attempted

    def test_keep_going_builds_the_rest(self, multi_project):
        handle = _stub_handle()
        handle.file_paths_for.side_effect = self._paths_for
        built = []

        def build(fp, requirement=None):
            stem = Path(fp).stem
            built.append(stem)
            return MagicMock(success=(stem != "db"), iterations=1)

        handle.build_from_feature.side_effect = build
        with patch("src.cli.factory.build_agent", return_value=handle):
            rc = cmd_tdd(_args(project=multi_project, keep_going=True))
        assert rc == 1
        assert built == ["db", "auth", "api"]

    def test_per_feature_playbook_scoping(self, multi_project):
        seen_playbook_ids = []
        handle = _stub_handle()
        handle.file_paths_for.side_effect = self._paths_for

        def fake_build_agent(config, skip_learn=False, model_ref=None):
            seen_playbook_ids.append(config.playbook_id)
            return handle

        with patch("src.cli.factory.build_agent", side_effect=fake_build_agent):
            cmd_tdd(_args(project=multi_project))
        assert seen_playbook_ids == [
            f"{multi_project.name}_db",
            f"{multi_project.name}_auth",
            f"{multi_project.name}_api",
        ]

    def test_cycle_is_reported(self, tmp_path, capsys):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        feats = tmp_path / "features"
        feats.mkdir()
        (feats / "a.feature").write_text("@depends_on(b)\nFeature: A\n\n  Scenario: s\n    Given x\n")
        (feats / "b.feature").write_text("@depends_on(a)\nFeature: B\n\n  Scenario: s\n    Given x\n")
        rc = cmd_tdd(_args(project=tmp_path))
        assert rc == 1
        assert "cycle" in capsys.readouterr().err

    def test_unknown_dependency_is_reported(self, tmp_path, capsys):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        feats = tmp_path / "features"
        feats.mkdir()
        (feats / "a.feature").write_text("@depends_on(ghost)\nFeature: A\n\n  Scenario: s\n    Given x\n")
        rc = cmd_tdd(_args(project=tmp_path))
        assert rc == 1
        assert "unknown node" in capsys.readouterr().err
