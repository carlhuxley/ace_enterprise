"""Project detection and analysis - determine project structure."""

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ProjectInfo:
    """Information about a detected Python project."""

    # Project root
    root: Path

    # Project name
    name: str

    # Source directory (where implementation code goes)
    src_dir: Path

    # Test directory (where test code goes)
    test_dir: Path

    # ACE directory (where ACE metadata goes)
    ace_dir: Path

    # Project type
    project_type: str  # "package" | "application" | "script"

    # Has git
    has_git: bool

    # Python version (if detectable)
    python_version: str | None = None

    # Package manager
    package_manager: str | None = None  # "poetry" | "pip" | "conda" | None


class ProjectDetector:
    """Detects and analyzes Python project structure."""

    def __init__(self, start_path: Path | None = None):
        """Initialize detector.

        Args:
            start_path: Path to start detection from (default: current directory)
        """
        self.start_path = start_path or Path.cwd()

    def detect(self) -> ProjectInfo:
        """Detect project structure.

        Returns:
            ProjectInfo with detected structure

        Raises:
            ValueError: If no valid project found
        """
        # Find project root
        root = self._find_project_root()

        # Determine project name
        name = self._detect_project_name(root)

        # Detect source directory
        src_dir = self._detect_src_dir(root)

        # Detect test directory
        test_dir = self._detect_test_dir(root)

        # ACE directory
        ace_dir = root / ".ace"

        # Project type
        project_type = self._detect_project_type(root)

        # Has git
        has_git = (root / ".git").exists()

        # Python version
        python_version = self._detect_python_version(root)

        # Package manager
        package_manager = self._detect_package_manager(root)

        info = ProjectInfo(
            root=root,
            name=name,
            src_dir=src_dir,
            test_dir=test_dir,
            ace_dir=ace_dir,
            project_type=project_type,
            has_git=has_git,
            python_version=python_version,
            package_manager=package_manager
        )

        logger.info(f"Detected project: {info.name} at {info.root}")
        logger.info(f"  Source: {info.src_dir}")
        logger.info(f"  Tests: {info.test_dir}")
        logger.info(f"  Type: {info.project_type}")

        return info

    def _find_project_root(self) -> Path:
        """Find project root directory.

        Walks up from start_path looking for project markers:
        - setup.py, setup.cfg
        - pyproject.toml
        - requirements.txt
        - .git directory

        Returns:
            Path to project root

        Raises:
            ValueError: If no project root found
        """
        current = self.start_path.resolve()

        # Walk up directory tree
        while current != current.parent:  # Stop at filesystem root
            # Check for project markers
            if self._is_project_root(current):
                return current
            current = current.parent

        # Check filesystem root
        if self._is_project_root(current):
            return current

        # No project found, use current directory
        logger.warning(f"No project markers found, using current directory: {self.start_path}")
        return self.start_path.resolve()

    def _is_project_root(self, path: Path) -> bool:
        """Check if path looks like a project root."""
        markers = [
            "setup.py",
            "setup.cfg",
            "pyproject.toml",
            "requirements.txt",
            ".git",
            "Pipfile",
            "poetry.lock",
        ]
        return any((path / marker).exists() for marker in markers)

    def _detect_project_name(self, root: Path) -> str:
        """Detect project name from various sources."""
        # Try pyproject.toml
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            try:
                import toml
                data = toml.load(pyproject)
                if "tool" in data and "poetry" in data["tool"]:
                    return data["tool"]["poetry"].get("name", root.name)
                if "project" in data:
                    return data["project"].get("name", root.name)
            except:
                pass

        # Try setup.py (look for name= in file)
        setup_py = root / "setup.py"
        if setup_py.exists():
            try:
                content = setup_py.read_text()
                # Simple regex to find name="..."
                import re
                match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    return match.group(1)
            except:
                pass

        # Use directory name
        return root.name

    def _detect_src_dir(self, root: Path) -> Path:
        """Detect source directory.

        Common patterns:
        - src/
        - {project_name}/
        - app/
        - Root directory itself
        """
        candidates = [
            root / "src",
            root / self._detect_project_name(root),
            root / "app",
            root,  # Last resort
        ]

        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                # Check if it looks like a Python package
                if candidate != root:
                    # Must have Python files or __init__.py
                    python_files = list(candidate.glob("*.py"))
                    if python_files or (candidate / "__init__.py").exists():
                        return candidate

        # Default to root
        return root

    def _detect_test_dir(self, root: Path) -> Path:
        """Detect test directory.

        Common patterns:
        - tests/
        - test/
        - Create if doesn't exist
        """
        candidates = [
            root / "tests",
            root / "test",
        ]

        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate

        # Default to tests/ (will be created)
        return root / "tests"

    def _detect_project_type(self, root: Path) -> str:
        """Detect project type.

        Returns:
            "package", "application", or "script"
        """
        # Has setup.py or pyproject.toml -> package
        if (root / "setup.py").exists() or (root / "pyproject.toml").exists():
            return "package"

        # Has main.py or app.py -> application
        if (root / "main.py").exists() or (root / "app.py").exists():
            return "application"

        # Has src/ directory -> package
        if (root / "src").exists():
            return "package"

        # Default
        return "script"

    def _detect_python_version(self, root: Path) -> str | None:
        """Detect Python version requirement.

        Checks:
        - pyproject.toml [tool.poetry.dependencies]
        - setup.py python_requires
        - .python-version
        """
        # Try .python-version
        python_version_file = root / ".python-version"
        if python_version_file.exists():
            return python_version_file.read_text().strip()

        # Try pyproject.toml
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            try:
                import toml
                data = toml.load(pyproject)
                if "tool" in data and "poetry" in data["tool"]:
                    python_dep = data["tool"]["poetry"]["dependencies"].get("python")
                    if python_dep:
                        return python_dep
            except:
                pass

        return None

    def _detect_package_manager(self, root: Path) -> str | None:
        """Detect package manager.

        Returns:
            "poetry", "pip", "conda", or None
        """
        if (root / "poetry.lock").exists():
            return "poetry"
        if (root / "Pipfile").exists() or (root / "Pipfile.lock").exists():
            return "pipenv"
        if (root / "conda.yml").exists() or (root / "environment.yml").exists():
            return "conda"
        if (root / "requirements.txt").exists():
            return "pip"
        return None

    def ensure_directories(self, info: ProjectInfo) -> None:
        """Ensure necessary directories exist.

        Creates:
        - src_dir (if doesn't exist)
        - test_dir (if doesn't exist)
        - ace_dir (if doesn't exist)
        - ace_dir/decisions (for ADRs)
        """
        # Source directory
        if not info.src_dir.exists():
            info.src_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created source directory: {info.src_dir}")

            # Create __init__.py for packages
            if info.project_type == "package":
                (info.src_dir / "__init__.py").touch()

        # Test directory
        if not info.test_dir.exists():
            info.test_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created test directory: {info.test_dir}")

            # Create __init__.py
            (info.test_dir / "__init__.py").touch()

        # ACE directory
        if not info.ace_dir.exists():
            info.ace_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created ACE directory: {info.ace_dir}")

        # ACE decisions directory
        decisions_dir = info.ace_dir / "decisions"
        if not decisions_dir.exists():
            decisions_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created decisions directory: {decisions_dir}")
