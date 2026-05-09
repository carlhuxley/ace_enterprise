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

        return cls(
            project_root=project_root,
            test_dir=test_dir,
            src_dir=src_dir,
            playbook_scope=scope,
            playbook_id=playbook_id,
            promote_threshold=float(raw.get("promote_threshold", 0.85)),
            max_iterations=int(raw.get("max_iterations", 20)),
        )


def _detect_dir(root: Path, candidates: list[str], default: str) -> Path:
    for name in candidates:
        candidate = root / name
        if candidate.is_dir():
            return candidate
    return root / default
