import textwrap
from pathlib import Path

import pytest

from src.utils.context_map import ASTSignature, ContextMap, ContextMapBuilder, FileSignatures


@pytest.fixture
def tmp_py(tmp_path):
    def write(name, content):
        p = tmp_path / name
        p.write_text(textwrap.dedent(content))
        return p
    return write


class TestContextMapBuilderSingleFile:
    def test_top_level_functions(self, tmp_py):
        f = tmp_py("foo.py", """
            def greet(name: str) -> str:
                return f"Hello {name}"

            def farewell(name: str, formal: bool = False) -> str:
                return f"Goodbye {name}"
        """)
        cm = ContextMapBuilder().build([f])
        names = {s.name for s in cm.files[f].signatures}
        assert names == {"greet", "farewell"}

    def test_function_signature_fields(self, tmp_py):
        f = tmp_py("foo.py", """
            def greet(name: str) -> str:
                return f"Hello {name}"
        """)
        cm = ContextMapBuilder().build([f])
        sig = cm.files[f].signatures[0]
        assert sig.kind == "function"
        assert sig.qualified_name == "greet"
        assert sig.parameters == ["name: str"]
        assert sig.return_annotation == "str"
        assert sig.source_file == f

    def test_function_default_parameter(self, tmp_py):
        f = tmp_py("foo.py", "def fn(x: int, y: int = 0) -> int:\n    pass\n")
        cm = ContextMapBuilder().build([f])
        sig = cm.files[f].signatures[0]
        assert any("y" in p and "0" in p for p in sig.parameters)

    def test_function_line_range(self, tmp_py):
        f = tmp_py("foo.py", """
            def first():
                pass

            def second():
                x = 1
                return x
        """)
        cm = ContextMapBuilder().build([f])
        sigs = {s.name: s for s in cm.files[f].signatures}
        assert sigs["first"].line_start < sigs["second"].line_start
        assert sigs["second"].line_end > sigs["second"].line_start

    def test_class_and_methods(self, tmp_py):
        f = tmp_py("bar.py", """
            class OrderProcessor:
                def process(self, order_id: int) -> bool:
                    pass

                def cancel(self, order_id: int, reason: str = "unknown") -> None:
                    pass
        """)
        cm = ContextMapBuilder().build([f])
        names = {s.qualified_name for s in cm.files[f].signatures}
        assert "OrderProcessor" in names
        assert "OrderProcessor.process" in names
        assert "OrderProcessor.cancel" in names

    def test_class_kind(self, tmp_py):
        f = tmp_py("bar.py", "class Foo:\n    pass\n")
        cm = ContextMapBuilder().build([f])
        cls = next(s for s in cm.files[f].signatures if s.name == "Foo")
        assert cls.kind == "class"

    def test_method_kind(self, tmp_py):
        f = tmp_py("bar.py", "class Foo:\n    def bar(self): pass\n")
        cm = ContextMapBuilder().build([f])
        method = next(s for s in cm.files[f].signatures if s.name == "bar")
        assert method.kind == "method"

    def test_imports_extracted(self, tmp_py):
        f = tmp_py("mod.py", """
            import os
            from pathlib import Path
            from typing import Optional as Opt
        """)
        cm = ContextMapBuilder().build([f])
        imports = cm.files[f].imports
        assert "os" in imports
        assert "pathlib.Path" in imports
        assert "Opt" in imports

    def test_vararg_and_kwarg(self, tmp_py):
        f = tmp_py("mod.py", "def fn(*args: str, **kwargs: int): pass\n")
        cm = ContextMapBuilder().build([f])
        sig = cm.files[f].signatures[0]
        param_str = " ".join(sig.parameters)
        assert "*args" in param_str
        assert "**kwargs" in param_str


class TestContextMapBuilderMultiFile:
    def test_multi_file(self, tmp_py):
        f1 = tmp_py("inventory.py", "def check_stock(item_id: int) -> int:\n    pass\n")
        f2 = tmp_py("payments.py", "def charge(amount: float) -> bool:\n    pass\n")
        cm = ContextMapBuilder().build([f1, f2])
        assert f1 in cm.files
        assert f2 in cm.files
        all_names = {s.name for s in cm.all_signatures()}
        assert "check_stock" in all_names
        assert "charge" in all_names

    def test_missing_file_skipped(self, tmp_path):
        missing = tmp_path / "nonexistent.py"
        cm = ContextMapBuilder().build([missing])
        assert missing not in cm.files

    def test_missing_file_does_not_affect_valid_files(self, tmp_py, tmp_path):
        good = tmp_py("good.py", "def foo(): pass\n")
        missing = tmp_path / "missing.py"
        cm = ContextMapBuilder().build([good, missing])
        assert good in cm.files
        assert {s.name for s in cm.files[good].signatures} == {"foo"}


class TestContextMapNodesRelevantTo:
    def test_returns_signatures_referenced_by_test(self, tmp_path):
        src = tmp_path / "inventory.py"
        src.write_text(
            "def check_stock(item_id: int) -> int:\n    return 42\n\n"
            "def unrelated() -> None:\n    pass\n"
        )
        test_file = tmp_path / "test_inventory.py"
        test_file.write_text(
            "def test_check_stock():\n"
            "    result = check_stock(1)\n"
            "    assert result == 42\n"
        )
        cm = ContextMapBuilder().build([src])
        relevant = cm.nodes_relevant_to([f"{test_file}::test_check_stock"])
        names = {s.name for s in relevant}
        assert "check_stock" in names
        assert "unrelated" not in names

    def test_missing_test_file_handled_gracefully(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def foo(): pass\n")
        cm = ContextMapBuilder().build([src])
        result = cm.nodes_relevant_to([str(tmp_path / "nonexistent.py") + "::test_foo"])
        assert isinstance(result, list)

    def test_empty_test_ids_returns_empty(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def foo(): pass\n")
        cm = ContextMapBuilder().build([src])
        assert cm.nodes_relevant_to([]) == []

    def test_multiple_test_ids_aggregate_results(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "def alpha(): pass\n"
            "def beta(): pass\n"
            "def gamma(): pass\n"
        )
        test_file = tmp_path / "test_mod.py"
        test_file.write_text(
            "def test_alpha():\n    alpha()\n\n"
            "def test_beta():\n    beta()\n"
        )
        cm = ContextMapBuilder().build([src])
        relevant = cm.nodes_relevant_to([
            f"{test_file}::test_alpha",
            f"{test_file}::test_beta",
        ])
        names = {s.name for s in relevant}
        assert "alpha" in names
        assert "beta" in names
        assert "gamma" not in names


class TestASTSignatureFormatCompact:
    def test_format_compact(self, tmp_py):
        f = tmp_py("mod.py", "def process(order_id: int) -> bool:\n    pass\n")
        cm = ContextMapBuilder().build([f])
        sig = cm.files[f].signatures[0]
        compact = sig.format_compact()
        assert "process" in compact
        assert "order_id" in compact
        assert "bool" in compact
