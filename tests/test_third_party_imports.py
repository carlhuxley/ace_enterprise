"""Tests for src/utils/third_party_imports.py (#53)."""

from src.utils.third_party_imports import infer_third_party_packages


def test_stdlib_imports_are_excluded():
    code = "import json\nfrom pathlib import Path\nimport collections\n"
    assert infer_third_party_packages([code]) == frozenset()


def test_third_party_import_is_detected():
    code = "from flask import Flask\napp = Flask(__name__)\n"
    assert infer_third_party_packages([code]) == frozenset({"flask"})


def test_mixed_stdlib_and_third_party():
    code = "import json\nimport gradio as gr\nfrom pathlib import Path\n"
    assert infer_third_party_packages([code]) == frozenset({"gradio"})


def test_known_local_sibling_modules_are_excluded():
    code = "from storage import load_data\nimport service\n"
    got = infer_third_party_packages([code], known_local_names={"storage", "service"})
    assert got == frozenset()


def test_import_name_mapped_to_pypi_package_name():
    code = "import yaml\nfrom PIL import Image\n"
    assert infer_third_party_packages([code]) == frozenset({"PyYAML", "Pillow"})


def test_unmapped_import_assumed_same_pypi_name():
    code = "import requests\n"
    assert infer_third_party_packages([code]) == frozenset({"requests"})


def test_multiple_code_blobs_are_merged():
    got = infer_third_party_packages(["import flask\n", "import gradio\n", "import json\n"])
    assert got == frozenset({"flask", "gradio"})


def test_unparseable_code_is_skipped_not_raised():
    got = infer_third_party_packages(["def broken(:\n", "import flask\n"])
    assert got == frozenset({"flask"})


def test_relative_imports_are_ignored():
    code = "from . import sibling\nfrom .sibling import thing\n"
    assert infer_third_party_packages([code]) == frozenset()
