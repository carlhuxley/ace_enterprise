"""Tests for src/utils/ast_shape.py."""

from src.utils.ast_shape import diff_protected_shapes, extract_protected_shape


class TestExtractClasses:
    def test_dataclass_bases_decorators_and_fields(self):
        shape = extract_protected_shape(
            "from dataclasses import dataclass\n\n"
            "@dataclass(frozen=True)\n"
            "class Point:\n"
            "    x: int\n"
            "    y: int = 0\n"
        )
        cls = shape.classes["Point"]
        assert cls.decorators == frozenset({"dataclass(frozen=True)"})
        assert cls.bases == frozenset()
        assert cls.fields["x"].annotation == "int"
        assert cls.fields["x"].default is None
        assert cls.fields["y"].default == "0"

    def test_protocol_bases_and_property_method(self):
        shape = extract_protected_shape(
            "from typing import Protocol, runtime_checkable\n\n"
            "@runtime_checkable\n"
            "class Thing(Protocol):\n"
            "    @property\n"
            "    def value(self) -> int: ...\n"
            "    def run(self, x: int) -> None: ...\n"
        )
        cls = shape.classes["Thing"]
        assert cls.bases == frozenset({"Protocol"})
        assert cls.decorators == frozenset({"runtime_checkable"})
        assert cls.methods["value"].is_property is True
        assert cls.methods["run"].is_property is False
        assert cls.methods["run"].args == "self, x: int"
        assert cls.methods["run"].returns == "None"

    def test_nested_statements_are_not_top_level_symbols(self):
        shape = extract_protected_shape(
            "def outer():\n"
            "    class Inner:\n"
            "        pass\n"
            "    return Inner\n"
        )
        assert shape.classes == {}
        assert "outer" in shape.functions


class TestExtractModuleLevel:
    def test_module_level_function(self):
        shape = extract_protected_shape("def greet(name: str) -> str:\n    ...\n")
        fn = shape.functions["greet"]
        assert fn.args == "name: str"
        assert fn.returns == "str"

    def test_module_level_constant(self):
        shape = extract_protected_shape("MAX: int = 10\n")
        const = shape.constants["MAX"]
        assert const.annotation == "int"
        assert const.value == "10"

    def test_module_level_type_alias(self):
        shape = extract_protected_shape("from typing import Callable\nHandler = Callable[[int], None]\n")
        assert shape.type_aliases["Handler"] == "Callable[[int], None]"


class TestDiffCompatibleChanges:
    def test_body_only_change_is_compatible(self):
        before = extract_protected_shape(
            "class Thing:\n    def run(self) -> int:\n        raise NotImplementedError\n"
        )
        after = extract_protected_shape(
            "class Thing:\n    def run(self) -> int:\n        return 42\n"
        )
        assert diff_protected_shapes(before, after) == []

    def test_new_methods_and_classes_are_compatible(self):
        before = extract_protected_shape("class Thing:\n    def run(self) -> int: ...\n")
        after = extract_protected_shape(
            "class Thing:\n"
            "    def run(self) -> int: ...\n"
            "    def helper(self) -> None: ...\n\n"
            "class Extra:\n    pass\n"
        )
        assert diff_protected_shapes(before, after) == []


class TestDiffViolations:
    def test_removed_class_is_a_violation(self):
        before = extract_protected_shape("class Thing:\n    pass\n")
        after = extract_protected_shape("x = 1\n")
        violations = diff_protected_shapes(before, after)
        assert any("Thing" in v and "removed" in v for v in violations)

    def test_changed_method_signature_is_a_violation(self):
        before = extract_protected_shape("class Thing:\n    def run(self, x: int) -> int: ...\n")
        after = extract_protected_shape("class Thing:\n    def run(self, x: str) -> int: ...\n")
        violations = diff_protected_shapes(before, after)
        assert any("run" in v and "signature changed" in v for v in violations)

    def test_renamed_method_is_a_violation(self):
        before = extract_protected_shape("class Thing:\n    def run(self) -> int: ...\n")
        after = extract_protected_shape("class Thing:\n    def go(self) -> int: ...\n")
        violations = diff_protected_shapes(before, after)
        assert any("run" in v and "removed" in v for v in violations)

    def test_changed_field_default_is_a_violation(self):
        before = extract_protected_shape(
            "from dataclasses import dataclass\n@dataclass\nclass Thing:\n    x: int = 1\n"
        )
        after = extract_protected_shape(
            "from dataclasses import dataclass\n@dataclass\nclass Thing:\n    x: int = 2\n"
        )
        violations = diff_protected_shapes(before, after)
        assert any("x" in v and "changed" in v for v in violations)

    def test_changed_base_class_is_a_violation(self):
        before = extract_protected_shape(
            "from typing import Protocol\nclass Thing(Protocol):\n    pass\n"
        )
        after = extract_protected_shape("class Thing:\n    pass\n")
        violations = diff_protected_shapes(before, after)
        assert any("bases changed" in v for v in violations)

    def test_changed_constant_value_is_a_violation(self):
        before = extract_protected_shape("MAX: int = 10\n")
        after = extract_protected_shape("MAX: int = 20\n")
        violations = diff_protected_shapes(before, after)
        assert any("MAX" in v and "changed" in v for v in violations)

    def test_changed_type_alias_is_a_violation(self):
        before = extract_protected_shape("Handler = int\n")
        after = extract_protected_shape("Handler = str\n")
        violations = diff_protected_shapes(before, after)
        assert any("Handler" in v and "changed" in v for v in violations)


class TestImportProtection:
    def test_from_import_is_recorded_per_bound_name(self):
        shape = extract_protected_shape("from discovery_tree import DiscoveryTree, WorkspaceSnapshot\n")
        assert shape.imports["DiscoveryTree"].module == "discovery_tree"
        assert shape.imports["DiscoveryTree"].imported_name == "DiscoveryTree"
        assert "WorkspaceSnapshot" in shape.imports

    def test_plain_import_is_recorded(self):
        shape = extract_protected_shape("import os\n")
        assert shape.imports["os"].module == "os"
        assert shape.imports["os"].imported_name is None

    def test_aliased_import_uses_local_name(self):
        shape = extract_protected_shape("from discovery_tree import DiscoveryTree as DT\n")
        assert "DT" in shape.imports
        assert "DiscoveryTree" not in shape.imports

    def test_import_wrapped_in_try_except_is_a_violation(self):
        """The exact real-world drift this closes: a real `ace project`
        run rewrapped a scaffold's clean top-level cross-module import into
        a defensive try/except-with-fallback block, which the AST lock did
        not originally catch since it only looked at true top-level
        statements. It must now."""
        before = extract_protected_shape("from discovery_tree import DiscoveryTree, WorkspaceSnapshot\n")
        after = extract_protected_shape(
            "WorkspaceSnapshot = Any\n"
            "DiscoveryTree = Any\n"
            "try:\n"
            "    from discovery_tree import DiscoveryTree, WorkspaceSnapshot\n"
            "except ImportError:\n"
            "    pass\n"
        )
        violations = diff_protected_shapes(before, after)
        assert any("DiscoveryTree" in v and "no longer a top-level import" in v for v in violations)
        assert any("WorkspaceSnapshot" in v and "no longer a top-level import" in v for v in violations)

    def test_added_import_is_compatible(self):
        before = extract_protected_shape("from typing import Any\n")
        after = extract_protected_shape("from typing import Any, Optional\n")
        assert diff_protected_shapes(before, after) == []

    def test_removed_name_from_shared_import_line_is_a_violation(self):
        before = extract_protected_shape("from typing import Any, Callable, runtime_checkable\n")
        after = extract_protected_shape("from typing import Any, Callable\n")
        violations = diff_protected_shapes(before, after)
        assert any("runtime_checkable" in v and "no longer a top-level import" in v for v in violations)

    def test_changed_source_module_is_a_violation(self):
        before = extract_protected_shape("from discovery_tree import DiscoveryTree\n")
        after = extract_protected_shape("from some_other_module import DiscoveryTree\n")
        violations = diff_protected_shapes(before, after)
        assert any("DiscoveryTree" in v and "changed from module" in v for v in violations)
