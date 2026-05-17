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
