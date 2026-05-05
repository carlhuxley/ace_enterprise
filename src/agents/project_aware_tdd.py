"""
Project-aware TDD module for intelligent file placement and code reuse.

Provides awareness of project structure to ensure:
- Files are placed in correct directories based on feature type
- Existing utilities and base classes are reused
- Project naming conventions are followed
"""

from dataclasses import dataclass, field


# Keyword to folder mappings for smart file placement
KEYWORD_FOLDER_MAPPINGS = {
    "broker": "src/broker",
    "routing": "src/broker",
    "orchestration": "src/broker",
    "agent": "src/agents",
    "autonomous": "src/agents",
    "storage": "src/storage",
    "repository": "src/storage",
    "persistence": "src/storage",
    "utility": "src/utils",
    "helper": "src/utils",
    "client": "src/utils",
}


@dataclass
class FolderInfo:
    """Information about a project folder."""

    path: str
    purpose: str


@dataclass
class ProjectStructure:
    """Represents the project folder structure with purposes."""

    folders: dict[str, FolderInfo] = field(default_factory=dict)

    def get_folder_for_keyword(self, keyword: str) -> str | None:
        """Get the appropriate folder for a keyword."""
        keyword_lower = keyword.lower()
        return KEYWORD_FOLDER_MAPPINGS.get(keyword_lower)

    def determine_file_placement(self, feature_requirement: str) -> str:
        """Determine where to place files based on feature requirement text."""
        requirement_lower = feature_requirement.lower()

        # Check each keyword mapping
        for keyword, folder in KEYWORD_FOLDER_MAPPINGS.items():
            if keyword in requirement_lower:
                return folder

        # Default to src/ if no specific match
        return "src"


class ProjectArchitecture:
    """Manages cached project architecture information."""

    def __init__(self):
        self._architecture = None
        self._structure: ProjectStructure | None = None

    def _fetch_architecture(self) -> dict:
        """Fetch architecture from knowledge graph (internal method)."""
        # TODO: Call codebase-memory-mcp get_architecture
        return {}

    def get_architecture(self) -> dict:
        """Get cached architecture, fetching if not cached."""
        if self._architecture is None:
            self._architecture = self._fetch_architecture()
        return self._architecture

    def get_structure(self) -> ProjectStructure:
        """Get project structure with folder purposes."""
        if self._structure is None:
            self._structure = ProjectStructure(
                folders={
                    "src/broker": FolderInfo("src/broker", "routing and orchestration"),
                    "src/agents": FolderInfo("src/agents", "autonomous agents"),
                    "src/storage": FolderInfo("src/storage", "persistence layer"),
                    "src/utils": FolderInfo("src/utils", "shared utilities"),
                }
            )
        return self._structure


class CodeReuseDetector:
    """Detects opportunities for code reuse in the project."""

    def __init__(self, project_name: str = "home-ch_dev-ace_enterprise"):
        self.project_name = project_name
        self._utility_cache: dict[str, list[str]] = {}

    def find_utilities(self, capability: str) -> list[str]:
        """
        Find existing utilities that provide a capability.

        Args:
            capability: What we need (e.g., "LLM generation", "embedding")

        Returns:
            List of qualified names of matching utilities
        """
        # TODO: Call search_graph to find existing utilities
        # For now, return cached or empty
        return self._utility_cache.get(capability, [])

    def find_base_classes(self, class_type: str) -> list[str]:
        """
        Find base classes that could be extended.

        Args:
            class_type: Type of class needed (e.g., "agent", "repository")

        Returns:
            List of base class qualified names
        """
        # TODO: Call search_graph with label=Class, name_pattern=Base*
        return []

    def suggest_imports(self, feature_requirement: str) -> list[str]:
        """
        Analyze feature requirement and suggest imports for reuse.

        Args:
            feature_requirement: Description of the feature

        Returns:
            List of suggested import statements
        """
        suggestions = []
        requirement_lower = feature_requirement.lower()

        # Check for common patterns
        if "llm" in requirement_lower or "generation" in requirement_lower:
            suggestions.append("from src.utils.llm_client import LLMClient")

        if "embedding" in requirement_lower:
            suggestions.append("from src.utils.embedding import EmbeddingService")

        if "playbook" in requirement_lower:
            suggestions.append("from src.storage.repository import PlaybookRepository")

        if "agent" in requirement_lower and "base" in requirement_lower:
            suggestions.append("from src.agents.base import BaseAgent")

        return suggestions


def extract_explicit_constraints(gherkin_content: str) -> dict[str, str]:
    """Extract explicit class name and file path from Gherkin Background.

    Parses statements like:
    "a new DynamicModelRouter class to be created in src/broker/dynamic_model_router.py"

    Args:
        gherkin_content: Full Gherkin feature file content

    Returns:
        Dictionary with 'class_name' and 'file_path' if found, empty dict otherwise
    """
    import re

    lines = gherkin_content.split("\n")
    in_background = False
    background_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("background:"):
            in_background = True
            continue
        if in_background:
            if stripped.startswith("Scenario:") or stripped.startswith("Scenario Outline:"):
                break
            if stripped:
                background_lines.append(stripped)

    background_text = " ".join(background_lines)

    # Pattern 1: "a new <ClassName> class to be created in <path>"
    match = re.search(
        r"a\s+new\s+(\w+)\s+class\s+to\s+be\s+created\s+in\s+([\w/_.-]+)",
        background_text, re.IGNORECASE,
    )
    if match:
        return {"class_name": match.group(1), "file_path": match.group(2)}

    # Pattern 2: "create a <ClassName> in <path>"
    match = re.search(
        r"create\s+a\s+(\w+)\s+in\s+([\w/_.-]+)",
        background_text, re.IGNORECASE,
    )
    if match:
        return {"class_name": match.group(1), "file_path": match.group(2)}

    # Pattern 3: "<ClassName> should be placed in <path>"
    match = re.search(
        r"(\w+)\s+should\s+be\s+placed\s+in\s+([\w/_.-]+)",
        background_text, re.IGNORECASE,
    )
    if match:
        return {"class_name": match.group(1), "file_path": match.group(2)}

    return {}
