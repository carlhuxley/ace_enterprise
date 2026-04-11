"""Tests for ImportValidator."""
import pytest
from pathlib import Path

from src.utils.import_validator import ImportValidator, ImportValidationError


@pytest.fixture
def validator():
    """Create validator with project root."""
    return ImportValidator(Path("/home/ch_dev/ace_enterprise"))


class TestExtractImports:
    """Tests for import extraction."""

    def test_extracts_from_import(self, validator):
        code = "from src.utils.llm_client import LLMClient"
        imports = validator.extract_imports(code)
        assert ("from", "src.utils.llm_client") in imports

    def test_extracts_regular_import(self, validator):
        code = "import os"
        imports = validator.extract_imports(code)
        assert ("import", "os") in imports

    def test_handles_syntax_error(self, validator):
        code = "from src.utils import ("  # Invalid syntax
        imports = validator.extract_imports(code)
        assert imports == []


class TestValidateImport:
    """Tests for single import validation."""

    def test_valid_import_path(self, validator):
        is_valid, suggestion = validator.validate_import("src.utils.llm_client")
        assert is_valid is True
        assert suggestion is None

    def test_invalid_import_path_with_suggestion(self, validator):
        is_valid, suggestion = validator.validate_import("src.markdown_importer")
        assert is_valid is False
        assert suggestion == "src.playbook.markdown_importer"

    def test_external_import_skipped(self, validator):
        is_valid, suggestion = validator.validate_import("os.path")
        assert is_valid is True
        assert suggestion is None


class TestFixImports:
    """Tests for automatic import fixing."""

    def test_fixes_wrong_import_path(self, validator):
        code = """from src.markdown_importer import MarkdownImporter

class Test:
    pass
"""
        fixed_code, corrections = validator.fix_imports(code)

        assert "from src.playbook.markdown_importer" in fixed_code
        assert len(corrections) == 1
        assert corrections[0] == ("src.markdown_importer", "src.playbook.markdown_importer")

    def test_leaves_valid_imports_unchanged(self, validator):
        code = """from src.utils.llm_client import LLMClient

class Test:
    pass
"""
        fixed_code, corrections = validator.fix_imports(code)

        assert fixed_code == code
        assert corrections == []


class TestValidateAndFix:
    """Tests for validate_and_fix method."""

    def test_auto_fixes_by_default(self, validator):
        code = "from src.markdown_importer import MarkdownImporter"
        fixed_code, corrections = validator.validate_and_fix(code)

        assert "src.playbook.markdown_importer" in fixed_code
        assert len(corrections) == 1

    def test_raises_when_auto_fix_disabled(self, validator):
        code = "from src.markdown_importer import MarkdownImporter"

        with pytest.raises(ImportValidationError) as exc_info:
            validator.validate_and_fix(code, auto_fix=False)

        assert "src.markdown_importer" in str(exc_info.value)
