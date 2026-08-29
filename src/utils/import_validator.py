"""
Import Path Validator for Generated Code.

Validates and corrects import paths in LLM-generated code to prevent
common errors like incorrect module paths.
"""
import ast
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ImportValidationError(Exception):
    """Raised when import validation fails and cannot be auto-corrected."""

    def __init__(self, invalid_imports: list[tuple[str, str | None]]):
        self.invalid_imports = invalid_imports
        messages = []
        for imp, suggestion in invalid_imports:
            if suggestion:
                messages.append(f"  {imp} -> {suggestion}")
            else:
                messages.append(f"  {imp} (no suggestion found)")
        super().__init__("Invalid import paths:\n" + "\n".join(messages))


class ImportValidator:
    """Validates and corrects import paths in generated code."""

    def __init__(self, project_root: Path | str):
        """
        Initialize the validator.

        Args:
            project_root: Root directory of the project
        """
        self.project_root = Path(project_root)
        self._module_cache: dict[str, Path] = {}
        self._build_module_cache()

    def _build_module_cache(self) -> None:
        """Build a cache of module names to their paths."""
        for py_file in self.project_root.glob("src/**/*.py"):
            if py_file.name == "__init__.py":
                continue
            module_name = py_file.stem
            if module_name not in self._module_cache:
                self._module_cache[module_name] = py_file

    def extract_imports(self, code: str) -> list[tuple[str, str]]:
        """
        Extract import statements from code.

        Args:
            code: Python source code

        Returns:
            List of (import_type, module_path) tuples
            import_type is 'import' or 'from'
        """
        imports = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(("import", alias.name))
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module:
                        imports.append(("from", module))
        except SyntaxError as e:
            logger.warning(f"Failed to parse code for import extraction: {e}")
        return imports

    def validate_import(self, import_path: str) -> tuple[bool, str | None]:
        """
        Validate a single import path.

        Args:
            import_path: The import path to validate (e.g., 'src.utils.llm_client')

        Returns:
            Tuple of (is_valid, suggested_correction)
            suggested_correction is None if valid or no suggestion found
        """
        # Skip external imports
        if not import_path.startswith("src"):
            return True, None

        parts = import_path.split(".")

        # Try as package (directory with __init__.py)
        package_path = self.project_root / "/".join(parts) / "__init__.py"
        if package_path.exists():
            return True, None

        # Try as module file
        module_path = self.project_root / "/".join(parts[:-1]) / f"{parts[-1]}.py"
        if module_path.exists():
            return True, None

        # Try direct path
        direct_path = self.project_root / ("/".join(parts) + ".py")
        if direct_path.exists():
            return True, None

        # Invalid - try to find suggestion
        target_module = parts[-1]
        if target_module in self._module_cache:
            correct_path = self._module_cache[target_module]
            rel_path = correct_path.relative_to(self.project_root)
            suggested = str(rel_path.with_suffix("")).replace("/", ".")
            return False, suggested

        return False, None

    def validate_code(self, code: str) -> list[tuple[str, bool, str | None]]:
        """
        Validate all imports in code.

        Args:
            code: Python source code

        Returns:
            List of (import_path, is_valid, suggestion) tuples
        """
        results = []
        imports = self.extract_imports(code)

        for imp_type, imp_path in imports:
            if imp_type == "from" and imp_path:
                is_valid, suggestion = self.validate_import(imp_path)
                results.append((imp_path, is_valid, suggestion))

        return results

    def fix_imports(self, code: str) -> tuple[str, list[tuple[str, str]]]:
        """
        Automatically fix invalid imports in code.

        Args:
            code: Python source code

        Returns:
            Tuple of (fixed_code, list of (old_import, new_import) corrections)
        """
        corrections = []
        fixed_code = code

        for imp_path, is_valid, suggestion in self.validate_code(code):
            if not is_valid and suggestion:
                # Replace the invalid import with the correct one
                fixed_code = fixed_code.replace(
                    f"from {imp_path}", f"from {suggestion}"
                )
                corrections.append((imp_path, suggestion))
                logger.info(f"Fixed import: {imp_path} -> {suggestion}")

        return fixed_code, corrections

    def validate_and_fix(
        self, code: str, auto_fix: bool = True
    ) -> tuple[str, list[tuple[str, str]]]:
        """
        Validate imports and optionally fix them.

        Args:
            code: Python source code
            auto_fix: Whether to automatically fix invalid imports

        Returns:
            Tuple of (possibly_fixed_code, corrections_made)

        Raises:
            ImportValidationError: If invalid imports found and auto_fix is False,
                                   or if invalid imports cannot be fixed
        """
        validation_results = self.validate_code(code)
        invalid_imports = [
            (imp, suggestion)
            for imp, is_valid, suggestion in validation_results
            if not is_valid
        ]

        if not invalid_imports:
            return code, []

        if not auto_fix:
            raise ImportValidationError(invalid_imports)

        # Try to fix
        fixed_code, corrections = self.fix_imports(code)

        # Verify fix worked
        remaining_invalid = [
            (imp, suggestion)
            for imp, is_valid, suggestion in self.validate_code(fixed_code)
            if not is_valid
        ]

        if remaining_invalid:
            raise ImportValidationError(remaining_invalid)

        return fixed_code, corrections
