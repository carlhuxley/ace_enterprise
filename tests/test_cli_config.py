import pytest
from pathlib import Path

from src.cli.config import ProjectConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project(tmp_path, dirs=(), config_yaml=None):
    """Create a minimal fake project under tmp_path."""
    for d in dirs:
        (tmp_path / d).mkdir(parents=True)
    if config_yaml is not None:
        ace_dir = tmp_path / ".ace"
        ace_dir.mkdir()
        (ace_dir / "config.yaml").write_text(config_yaml)
    return tmp_path


# ---------------------------------------------------------------------------
# playbook_id defaults
# ---------------------------------------------------------------------------

def test_playbook_id_defaults_to_project_dir_name(tmp_path):
    project = _project(tmp_path)
    config = ProjectConfig.load(project)
    assert config.playbook_id == project.name


def test_playbook_id_read_from_config_file(tmp_path):
    project = _project(tmp_path, config_yaml="playbook_id: my-app\n")
    config = ProjectConfig.load(project)
    assert config.playbook_id == "my-app"


# ---------------------------------------------------------------------------
# playbook_scope defaults
# ---------------------------------------------------------------------------

def test_playbook_scope_defaults_to_both(tmp_path):
    config = ProjectConfig.load(_project(tmp_path))
    assert config.playbook_scope == "both"


def test_playbook_scope_read_from_config_file(tmp_path):
    project = _project(tmp_path, config_yaml="playbook: local\n")
    config = ProjectConfig.load(project)
    assert config.playbook_scope == "local"


def test_playbook_scope_rejects_invalid_value(tmp_path):
    project = _project(tmp_path, config_yaml="playbook: nonsense\n")
    with pytest.raises(ValueError, match="playbook"):
        ProjectConfig.load(project)


# ---------------------------------------------------------------------------
# test_dir auto-detection
# ---------------------------------------------------------------------------

def test_test_dir_detected_as_tests(tmp_path):
    project = _project(tmp_path, dirs=["tests"])
    config = ProjectConfig.load(project)
    assert config.test_dir == project / "tests"


def test_test_dir_falls_back_to_test(tmp_path):
    project = _project(tmp_path, dirs=["test"])
    config = ProjectConfig.load(project)
    assert config.test_dir == project / "test"


def test_test_dir_defaults_to_tests_when_neither_exists(tmp_path):
    project = _project(tmp_path)
    config = ProjectConfig.load(project)
    assert config.test_dir == project / "tests"


def test_test_dir_prefers_tests_over_test(tmp_path):
    project = _project(tmp_path, dirs=["tests", "test"])
    config = ProjectConfig.load(project)
    assert config.test_dir == project / "tests"


# ---------------------------------------------------------------------------
# src_dir auto-detection
# ---------------------------------------------------------------------------

def test_src_dir_detected_as_src(tmp_path):
    project = _project(tmp_path, dirs=["src"])
    config = ProjectConfig.load(project)
    assert config.src_dir == project / "src"


def test_src_dir_falls_back_to_lib(tmp_path):
    project = _project(tmp_path, dirs=["lib"])
    config = ProjectConfig.load(project)
    assert config.src_dir == project / "lib"


def test_src_dir_defaults_to_src_when_none_found(tmp_path):
    project = _project(tmp_path)
    config = ProjectConfig.load(project)
    assert config.src_dir == project / "src"


# ---------------------------------------------------------------------------
# other defaults
# ---------------------------------------------------------------------------

def test_promote_threshold_defaults(tmp_path):
    config = ProjectConfig.load(_project(tmp_path))
    assert config.promote_threshold == pytest.approx(0.85)


def test_max_iterations_defaults(tmp_path):
    config = ProjectConfig.load(_project(tmp_path))
    assert config.max_iterations == 20


def test_promote_threshold_read_from_config_file(tmp_path):
    project = _project(tmp_path, config_yaml="promote_threshold: 0.9\n")
    config = ProjectConfig.load(project)
    assert config.promote_threshold == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# feature file discovery
# ---------------------------------------------------------------------------

def test_discover_features_finds_feature_files(tmp_path):
    project = _project(tmp_path, dirs=["features"])
    (project / "features" / "checkout.feature").write_text("Feature: checkout\n")
    (project / "features" / "login.feature").write_text("Feature: login\n")
    config = ProjectConfig.load(project)
    found = config.discover_features()
    assert len(found) == 2
    assert all(f.suffix == ".feature" for f in found)


def test_discover_features_returns_empty_when_no_features_dir(tmp_path):
    config = ProjectConfig.load(_project(tmp_path))
    assert config.discover_features() == []


def test_discover_features_searches_project_root_as_fallback(tmp_path):
    project = _project(tmp_path)
    (project / "checkout.feature").write_text("Feature: checkout\n")
    config = ProjectConfig.load(project)
    found = config.discover_features()
    assert len(found) == 1
