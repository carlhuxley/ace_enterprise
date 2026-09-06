"""ProjectConfig — loads .ace/config.yaml and auto-detects project layout."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

_VALID_SCOPES = {"local", "global", "both"}
_TEST_DIR_CANDIDATES = ["tests", "test"]
_SRC_DIR_CANDIDATES = ["src", "lib"]


@dataclass
class ProjectConfig:
    project_root: Path
    test_dir: Path
    src_dir: Path
    playbook_scope: str = "both"
    playbook_id: str = ""
    promote_threshold: float = 0.85
    max_iterations: int = 20
    team_id: str | None = None
    # "<provider>/<model>" refs. With 2+, build_agent() routes the run to one
    # of them via the AdaptiveBroker (audit-history-driven); with 0 or 1 the
    # single configured model / ACE default is used unchanged.
    candidate_models: list[str] = field(default_factory=list)
    # Per-role "<provider>/<model>" refs for `ace project` (issue #40). Empty
    # string means "not configured" -- cmd_project resolves the fallback
    # chain (architect/worker fall back to the routed/default base model,
    # repair falls back to worker_model, escalation has no fallback and
    # simply stays disabled). Deliberately left as plain strings here, not
    # resolved to a client or defaulted to each other -- this dataclass is a
    # literal reflection of the YAML; fallback resolution happens once, at
    # the wiring layer, not duplicated here too.
    architect_model: str = ""
    worker_model: str = ""
    repair_model: str = ""
    escalation_model: str = ""

    def discover_features(self) -> list[Path]:
        """Return all .feature files in <project>/features/, falling back to project root."""
        features_dir = self.project_root / "features"
        if features_dir.is_dir():
            return sorted(features_dir.glob("*.feature"))
        return sorted(self.project_root.glob("*.feature"))

    @classmethod
    def load(cls, project_root: Path) -> ProjectConfig:
        raw: dict = {}
        config_file = project_root / ".ace" / "config.yaml"
        if config_file.exists():
            if yaml is None:
                raise RuntimeError("PyYAML is required to read .ace/config.yaml")
            raw = yaml.safe_load(config_file.read_text()) or {}

        scope = raw.get("playbook", "both")
        if scope not in _VALID_SCOPES:
            raise ValueError(
                f"playbook must be one of {_VALID_SCOPES}, got {scope!r}"
            )

        playbook_id = raw.get("playbook_id", project_root.name)

        test_dir = _detect_dir(project_root, _TEST_DIR_CANDIDATES, default="tests")
        src_dir = _detect_dir(project_root, _SRC_DIR_CANDIDATES, default="src")

        architect_model = _validate_model_ref("architect_model", raw.get("architect_model", ""))
        worker_model = _validate_model_ref("worker_model", raw.get("worker_model", ""))
        repair_model = _validate_model_ref("repair_model", raw.get("repair_model", ""))
        escalation_model = _validate_model_ref("escalation_model", raw.get("escalation_model", ""))

        return cls(
            project_root=project_root,
            test_dir=test_dir,
            src_dir=src_dir,
            playbook_scope=scope,
            playbook_id=playbook_id,
            promote_threshold=float(raw.get("promote_threshold", 0.85)),
            max_iterations=int(raw.get("max_iterations", 20)),
            team_id=raw.get("team_id"),
            candidate_models=_str_list(raw.get("candidate_models")),
            architect_model=architect_model,
            worker_model=worker_model,
            repair_model=repair_model,
            escalation_model=escalation_model,
        )


def _validate_model_ref(field_name: str, value: object) -> str:
    """Validate an optional per-role model ref ("<provider>/<model>" or
    "claude-cli[/<model>]"). Empty/unset means "not configured" and is
    always valid -- validation only applies once a ref is actually given.

    _split_model_ref is imported locally, not at module scope: factory.py
    already imports ProjectConfig at module level, so a module-level import
    the other way would be circular.
    """
    ref = str(value).strip() if value else ""
    if not ref:
        return ""
    from src.cli.factory import _split_model_ref

    _split_model_ref(ref)  # raises ValueError with its own message on a bad ref
    return ref


def _str_list(value: object) -> list[str]:
    """Coerce a YAML scalar or sequence into a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    raise ValueError(f"expected a string or list of strings, got {type(value).__name__}")


def _detect_dir(root: Path, candidates: list[str], default: str) -> Path:
    for name in candidates:
        candidate = root / name
        if candidate.is_dir():
            return candidate
    return root / default
