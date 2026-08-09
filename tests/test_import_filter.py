import pytest
from src.agents.import_filter import ImportFilter, ForbiddenImportError


@pytest.fixture
def f():
    return ImportFilter()


def test_direct_import_blocked(f):
    with pytest.raises(ForbiddenImportError, match="os"):
        f.check("import os")


def test_from_import_blocked(f):
    with pytest.raises(ForbiddenImportError, match="subprocess"):
        f.check("from subprocess import run")


def test_aliased_import_blocked(f):
    with pytest.raises(ForbiddenImportError, match="os"):
        f.check("import os as operating_system")


def test_nested_import_blocked(f):
    with pytest.raises(ForbiddenImportError, match="os"):
        f.check("import os.path")


def test_from_nested_import_blocked(f):
    with pytest.raises(ForbiddenImportError, match="os"):
        f.check("from os.path import join")


def test_eval_call_blocked(f):
    with pytest.raises(ForbiddenImportError, match="eval"):
        f.check("result = eval('1+1')")


def test_exec_call_blocked(f):
    with pytest.raises(ForbiddenImportError, match="exec"):
        f.check("exec('x = 1')")


def test_clean_code_passes(f):
    f.check("import json\nfrom pathlib import Path\nx = 1 + 1")


def test_custom_blocklist():
    f = ImportFilter(blocklist=["requests"])
    with pytest.raises(ForbiddenImportError, match="requests"):
        f.check("import requests")
    # default blocklist no longer active
    f.check("import os")


def test_syntax_error_raises_syntax_error_not_forbidden(f):
    with pytest.raises(SyntaxError):
        f.check("def broken(:")


# ---------------------------------------------------------------------------
# Dynamic import bypasses (ace_enterprise-dwt)
# ---------------------------------------------------------------------------

def test_dunder_import_blocked(f):
    with pytest.raises(ForbiddenImportError, match="os"):
        f.check("__import__('os')")


def test_dunder_import_non_blocked_module_passes(f):
    f.check("__import__('json')")


def test_importlib_import_module_blocked(f):
    with pytest.raises(ForbiddenImportError, match="subprocess"):
        f.check("import importlib\nimportlib.import_module('subprocess')")


def test_importlib_import_module_blocked_without_explicit_import(f):
    with pytest.raises(ForbiddenImportError, match="os"):
        f.check("importlib.import_module('os')")


def test_importlib_import_module_non_blocked_module_passes(f):
    f.check("import importlib\nimportlib.import_module('json')")


def test_aliased_importlib_module_call_blocked(f):
    with pytest.raises(ForbiddenImportError, match="os"):
        f.check("import importlib as il\nil.import_module('os')")


def test_aliased_import_module_function_blocked(f):
    with pytest.raises(ForbiddenImportError, match="subprocess"):
        f.check("from importlib import import_module as loader\nloader('subprocess')")


def test_dynamic_import_with_non_literal_arg_does_not_crash(f):
    # Not statically detectable — the filter is advisory, not a full interpreter.
    # Must not raise ForbiddenImportError (can't prove it's forbidden) and must
    # not crash on a non-Constant argument.
    f.check("mod_name = get_module_name()\n__import__(mod_name)")
