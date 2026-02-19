"""Project configuration - .ace/config.yml schema and management."""

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ACEConfig:
    """ACE configuration for a project (.ace/config.yml)."""

    # Project metadata
    project_name: str
    project_domain: str | None = None  # "healthcare", "fintech", "e-commerce", etc.
    project_tags: list[str] = field(default_factory=list)

    # Central knowledge configuration
    use_central_knowledge: bool = True
    central_knowledge_path: str | None = None  # Default: ~/.ace/knowledge

    # Playbook configuration
    playbooks: list[str] = field(default_factory=list)  # ["global", "healthcare", "python"]

    # Local customizations
    local_playbook: str | None = None  # Path to project-specific playbook

    # Code generation preferences
    test_framework: str = "pytest"  # "pytest", "unittest", "nose"
    code_style: str = "pep8"  # "pep8", "google", "numpy"
    type_hints: bool = True
    docstrings: bool = True

    # TDD preferences
    tdd_cycles: int = 3  # Max TDD cycles
    auto_fix: bool = True  # Auto-fix simple issues

    # Provenance
    contributors: list[str] = field(default_factory=list)  # ["user@company.com"]
    ai_models: list[dict[str, str]] = field(default_factory=list)  # [{"provider": "...", "model": "..."}]

    # Git integration
    auto_stage: bool = False  # Auto-stage generated files
    auto_commit: bool = False  # Auto-commit (generally should be False)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ACEConfig':
        """Load from dictionary."""
        return cls(**data)

    def save(self, filepath: Path) -> None:
        """Save configuration to YAML file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)
        logger.info(f"Saved ACE config to: {filepath}")

    @classmethod
    def load(cls, filepath: Path) -> 'ACEConfig':
        """Load configuration from YAML file."""
        with open(filepath) as f:
            data = yaml.safe_load(f)
        logger.info(f"Loaded ACE config from: {filepath}")
        return cls.from_dict(data)

    @classmethod
    def create_default(cls, project_name: str, project_domain: str | None = None) -> 'ACEConfig':
        """Create default configuration for a project."""
        return cls(
            project_name=project_name,
            project_domain=project_domain,
            project_tags=[],
            use_central_knowledge=True,
            playbooks=["global"],  # Start with global playbook
            test_framework="pytest",
            code_style="pep8",
            type_hints=True,
            docstrings=True,
            tdd_cycles=3,
            auto_fix=True,
            auto_stage=False,
            auto_commit=False,
        )


class ProjectConfig:
    """Manages project configuration."""

    def __init__(self, project_root: Path):
        """Initialize project configuration manager.

        Args:
            project_root: Root directory of project
        """
        self.project_root = project_root
        self.ace_dir = project_root / ".ace"
        self.config_file = self.ace_dir / "config.yml"

    def exists(self) -> bool:
        """Check if ACE configuration exists for this project."""
        return self.config_file.exists()

    def load(self) -> ACEConfig:
        """Load ACE configuration.

        Returns:
            ACEConfig

        Raises:
            FileNotFoundError: If config doesn't exist
        """
        if not self.exists():
            raise FileNotFoundError(f"No ACE config found at: {self.config_file}")
        return ACEConfig.load(self.config_file)

    def save(self, config: ACEConfig) -> None:
        """Save ACE configuration.

        Args:
            config: ACE configuration to save
        """
        config.save(self.config_file)

    def initialize(
        self,
        project_name: str,
        project_domain: str | None = None,
        **kwargs
    ) -> ACEConfig:
        """Initialize ACE for this project.

        Creates .ace/ directory and config.yml if they don't exist.

        Args:
            project_name: Name of project
            project_domain: Domain of project (optional)
            **kwargs: Additional config options

        Returns:
            ACEConfig that was created

        Raises:
            ValueError: If ACE already initialized
        """
        if self.exists():
            raise ValueError(f"ACE already initialized at: {self.ace_dir}")

        # Create .ace directory
        self.ace_dir.mkdir(parents=True, exist_ok=True)

        # Create decisions directory
        (self.ace_dir / "decisions").mkdir(exist_ok=True)

        # Create default config
        config = ACEConfig.create_default(project_name, project_domain)

        # Apply overrides
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)

        # Save config
        self.save(config)

        # Create README
        readme = self.ace_dir / "README.md"
        readme.write_text(f"""# ACE Configuration

This directory contains ACE Enterprise metadata for the `{project_name}` project.

## Structure

- `config.yml` - ACE configuration
- `decisions/` - Architectural Decision Records (ADRs)

## Usage

To build a feature:
```bash
ace build-feature path/to/feature.feature
```

To view decisions:
```bash
ls .ace/decisions/
```

## Documentation

- [ACE Strategic Plan](https://github.com/carlhuxley/ace_enterprise/blob/main/docs/ACE_STRATEGIC_PLAN.md)
- [Gherkin-Driven TDD](https://github.com/carlhuxley/ace_enterprise/blob/main/docs/gherkin_driven_unit_tests.md)
""")

        logger.info(f"Initialized ACE for project: {project_name}")
        logger.info(f"  Config: {self.config_file}")
        logger.info(f"  Decisions: {self.ace_dir / 'decisions'}")

        return config

    def get_or_create(self, project_name: str, **kwargs) -> ACEConfig:
        """Get existing config or create default.

        Args:
            project_name: Project name (used if creating)
            **kwargs: Additional config options (used if creating)

        Returns:
            ACEConfig
        """
        if self.exists():
            return self.load()
        else:
            return self.initialize(project_name, **kwargs)
