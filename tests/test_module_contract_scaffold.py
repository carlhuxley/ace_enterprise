"""Tests for src/contracts/module_contract_scaffold.py."""

import ast

from src.contracts.module_contract_scaffold import scaffold_module
from src.contracts.module_contract_schema import ContractDocument


def _scaffold(yaml_text: str, dependency_exports=None) -> str:
    doc = ContractDocument.from_yaml(yaml_text)
    return scaffold_module(doc, dependency_exports=dependency_exports)


class TestEmitPerKind:
    def test_frozen_dataclass(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Point\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: x\n        type: int\n"
        )
        ast.parse(src)
        assert "@dataclass(frozen=True)" in src
        assert "class Point:" in src
        assert "x: int" in src

    def test_mutable_dataclass_pydantic_model(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Node\n    kind: mutable_dataclass\n    impl: pydantic_model\n"
            "    fields:\n      - name: x\n        type: int\n"
        )
        ast.parse(src)
        assert "class Node(BaseModel):" in src
        assert "ConfigDict(frozen=True)" not in src

    def test_frozen_pydantic_model_sets_config_dict_frozen(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Node\n    kind: frozen_dataclass\n    impl: pydantic_model\n"
            "    fields:\n      - name: x\n        type: int\n"
        )
        assert "model_config = ConfigDict(frozen=True)" in src

    def test_protocol_with_property(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Thing\n    kind: protocol\n"
            "    methods:\n"
            "      - name: value\n        property: true\n        signature: \"value -> int\"\n"
        )
        ast.parse(src)
        assert "@runtime_checkable" in src
        assert "class Thing(Protocol):" in src
        assert "@property" in src

    def test_abc_emits_abstractmethod_stubs(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Base\n    kind: abc\n"
            "    constructor:\n      params:\n        - name: config\n          type: dict\n"
            "    methods:\n      - name: run\n        signature: \"run(self) -> None\"\n"
        )
        ast.parse(src)
        assert "class Base(ABC):" in src
        assert "@abstractmethod" in src

    def test_concrete_class_constructor_and_body_stub(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Widget\n    kind: concrete_class\n"
            "    constructor:\n      params:\n        - name: size\n          type: int\n"
            "    methods:\n      - name: grow\n        signature: \"grow(self) -> None\"\n"
        )
        ast.parse(src)
        assert "def __init__(self, size: int) -> None:" in src
        assert "self._size = size" in src
        assert "NotImplementedError" in src

    def test_type_alias(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Handler\n    kind: type_alias\n    definition: \"Callable[[int], None]\"\n"
        )
        ast.parse(src)
        assert "Handler = Callable[[int], None]" in src

    def test_function(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: greet\n    kind: function\n    signature: \"(name: str) -> str\"\n"
        )
        ast.parse(src)
        assert "def greet(name: str) -> str:" in src

    def test_numeric_constant_emitted_as_literal(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: MAX\n    kind: constant\n    type: float\n    value: \"-1.0\"\n"
        )
        ast.parse(src)
        assert "MAX: float = -1.0" in src

    def test_string_constant_emitted_as_repr(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: LABEL\n    kind: constant\n    type: str\n    value: \"hello\"\n"
        )
        ast.parse(src)
        assert "LABEL: str = 'hello'" in src


class TestCrossModuleImports:
    def test_dependency_exports_emit_sorted_import_line(self):
        src = _scaffold(
            "module: gadget\ndepends_on: [widget]\npublic_api:\n"
            "  - name: Gadget\n    kind: concrete_class\n"
            "    constructor:\n      params:\n        - name: w\n          type: Widget\n",
            dependency_exports={"widget": ["Widget", "AnotherType"]},
        )
        ast.parse(src)
        assert "from widget import AnotherType, Widget" in src

    def test_multiple_dependencies_sorted_by_module_name(self):
        src = _scaffold(
            "module: m\npublic_api:\n  - name: X\n    kind: type_alias\n    definition: int\n",
            dependency_exports={"zeta": ["Z"], "alpha": ["A"]},
        )
        assert "from alpha import A\nfrom zeta import Z" in src

    def test_no_dependency_exports_emits_no_import_lines(self):
        src = _scaffold("module: m\npublic_api:\n  - name: X\n    kind: type_alias\n    definition: int\n")
        assert "import" not in src.split("ConfigDict = dict", 1)[1].split("X = int", 1)[0]

    def test_dependency_with_no_exported_names_is_skipped(self):
        src = _scaffold(
            "module: m\npublic_api:\n  - name: X\n    kind: type_alias\n    definition: int\n",
            dependency_exports={"empty_dep": []},
        )
        assert "empty_dep" not in src


class TestFullContractRoundTrip:
    def test_every_entry_kind_together_parses_as_valid_python(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: MAX\n    kind: constant\n    type: int\n    value: \"5\"\n"
            "  - name: Handler\n    kind: type_alias\n    definition: \"Callable[[int], None]\"\n"
            "  - name: Point\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: x\n        type: int\n"
            "  - name: Thing\n    kind: protocol\n"
            "    methods:\n      - name: run\n        signature: \"run(self) -> None\"\n"
            "  - name: Base\n    kind: abc\n"
            "    methods:\n      - name: run\n        signature: \"run(self) -> None\"\n"
            "  - name: Widget\n    kind: concrete_class\n"
            "    constructor:\n      params: []\n"
            "  - name: greet\n    kind: function\n    signature: \"(name: str) -> str\"\n"
        )
        ast.parse(src)
