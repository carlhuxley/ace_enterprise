
import pytest

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


def test_team_id_defaults_to_none(tmp_path):
    config = ProjectConfig.load(_project(tmp_path))
    assert config.team_id is None


def test_team_id_read_from_config_file(tmp_path):
    project = _project(tmp_path, config_yaml="team_id: payments\n")
    config = ProjectConfig.load(project)
    assert config.team_id == "payments"


# ---------------------------------------------------------------------------
# candidate_models (AdaptiveBroker routing)
# ---------------------------------------------------------------------------

def test_candidate_models_defaults_to_empty_list(tmp_path):
    config = ProjectConfig.load(_project(tmp_path))
    assert config.candidate_models == []


def test_candidate_models_read_as_list(tmp_path):
    project = _project(
        tmp_path,
        config_yaml=(
            "candidate_models:\n"
            "  - openrouter/qwen/qwen3-coder:free\n"
            "  - ollama/qwen2.5-coder:7b\n"
        ),
    )
    config = ProjectConfig.load(project)
    assert config.candidate_models == [
        "openrouter/qwen/qwen3-coder:free",
        "ollama/qwen2.5-coder:7b",
    ]


def test_candidate_models_scalar_is_coerced_to_single_entry_list(tmp_path):
    project = _project(tmp_path, config_yaml="candidate_models: ollama/qwen2.5-coder:7b\n")
    config = ProjectConfig.load(project)
    assert config.candidate_models == ["ollama/qwen2.5-coder:7b"]


def test_candidate_models_rejects_non_string_scalar(tmp_path):
    project = _project(tmp_path, config_yaml="candidate_models: 42\n")
    with pytest.raises(ValueError, match="string or list"):
        ProjectConfig.load(project)


# ---------------------------------------------------------------------------
# per-role model fields (issue #40): architect_model / worker_model /
# repair_model / escalation_model
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field_name", ["architect_model", "worker_model", "repair_model", "escalation_model"])
class TestRoleModelFields:
    def test_defaults_to_empty_string(self, tmp_path, field_name):
        config = ProjectConfig.load(_project(tmp_path))
        assert getattr(config, field_name) == ""

    def test_read_from_config_file(self, tmp_path, field_name):
        project = _project(tmp_path, config_yaml=f"{field_name}: openrouter/qwen/qwen3-coder:free\n")
        config = ProjectConfig.load(project)
        assert getattr(config, field_name) == "openrouter/qwen/qwen3-coder:free"

    def test_accepts_claude_cli_ref(self, tmp_path, field_name):
        project = _project(tmp_path, config_yaml=f"{field_name}: claude-cli/haiku\n")
        config = ProjectConfig.load(project)
        assert getattr(config, field_name) == "claude-cli/haiku"

    def test_rejects_invalid_ref(self, tmp_path, field_name):
        project = _project(tmp_path, config_yaml=f"{field_name}: justqwen\n")
        with pytest.raises(ValueError, match="<provider>/<model>"):
            ProjectConfig.load(project)


def test_repair_model_does_not_fall_back_to_worker_model_at_the_config_layer(tmp_path):
    """ProjectConfig is a literal reflection of the YAML -- the worker_model
    fallback for an unset repair_model is a wiring-layer concern (cmd_project/
    ProjectBuilder), not something ProjectConfig itself should resolve."""
    project = _project(tmp_path, config_yaml="worker_model: openrouter/qwen/qwen3-coder:free\n")
    config = ProjectConfig.load(project)
    assert config.repair_model == ""


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
