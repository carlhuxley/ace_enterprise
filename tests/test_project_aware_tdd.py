# Test file for project_aware_tdd
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.broker.project_aware_tdd import *

def test_project_architecture_has_get_architecture_method():
    architecture = ProjectArchitecture()
    assert hasattr(architecture, 'get_architecture')

def test_project_architecture_caches_structure():
    architecture = ProjectArchitecture()
    with patch.object(architecture, '_get_structure_map', return_value={"cached": True}) as mock_get:
        # First call should call the method
        result1 = architecture.get_architecture()
        # Second call should use cache
        result2 = architecture.get_architecture()
        # Assert mock was called only once
        mock_get.assert_called_once()
        # Results should be same (from cache)
        assert result1 == result2

def test_project_architecture_caches_structure_map():
    architecture = ProjectArchitecture()
    with patch.object(architecture, '_get_structure_map', return_value={
        "folders": {
            "src": {"purpose": "source code", "permissions": "755"},
            "tests": {"purpose": "testing", "permissions": "644"},
            "docs": {"purpose": "documentation", "permissions": "755"}
        },
        "files": {
            "main.py": {"type": "module", "size": 1024, "checksum": "abc123"},
            "config.json": {"type": "config", "size": 512, "checksum": "def456"},
            "README.md": {"type": "document", "size": 2048, "checksum": "ghi789"}
        },
        "symlinks": {
            "current": {"target": "v1.2.3", "permissions": "777"}
        }
    }) as mock_get:
        result = architecture.get_architecture()
        # Verify new symlinks section exists
        assert "symlinks" in result
        assert result["symlinks"]["current"] == {"target": "v1.2.3", "permissions": "777"}
        # Verify new file metadata (checksums)
        assert result["files"]["main.py"]["checksum"] == "abc123"
        assert result["files"]["config.json"]["checksum"] == "def456"
        # Verify new folder exists
        assert "docs" in result["folders"]
        # Verify complete structure with new elements
        assert set(result["folders"].keys()) == {"src", "tests", "docs"}
        assert set(result["files"].keys()) == {"main.py", "config.json", "README.md"}
        assert set(result["symlinks"].keys()) == {"current"}