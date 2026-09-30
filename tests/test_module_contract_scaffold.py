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


class TestFixtureFactories:
    def test_dataclass_with_fields_gets_a_fixture_factory(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Point\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: x\n        type: int\n      - name: y\n        type: str\n"
        )
        ast.parse(src)
        assert "def make_valid_point(**overrides) -> Point:" in src
        assert "x=0," in src
        assert "y=''," in src
        assert "defaults.update(overrides)" in src
        assert "return Point(**defaults)" in src

    def test_dataclass_with_no_fields_gets_no_factory(self):
        src = _scaffold("module: m\npublic_api:\n  - name: Empty\n    kind: frozen_dataclass\n")
        assert "make_valid_empty" not in src

    def test_concrete_class_gets_no_factory(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Widget\n    kind: concrete_class\n"
            "    constructor:\n      params:\n        - name: size\n          type: int\n"
        )
        assert "make_valid_widget" not in src

    def test_contract_declared_default_is_reused_verbatim(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Config\n    kind: mutable_dataclass\n"
            "    fields:\n      - name: retries\n        type: int\n        default: \"3\"\n"
        )
        assert "retries=3," in src

    def test_optional_field_defaults_to_none(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Thing\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: score\n        type: \"float | None\"\n"
        )
        assert "score=None," in src

    def test_literal_field_uses_first_element(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Task\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: status\n        type: 'Literal[\"pending\", \"done\"]'\n"
        )
        ast.parse(src)
        assert 'status="pending",' in src

    def test_dict_and_list_prefixed_types_default_to_empty_collections(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Thing\n    kind: frozen_dataclass\n"
            "    fields:\n"
            "      - name: tags\n        type: \"list[str]\"\n"
            "      - name: meta\n        type: \"dict[str, Any]\"\n"
        )
        assert "tags=[]," in src
        assert "meta={}," in src

    def test_required_nested_entry_reference_calls_its_factory(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Snapshot\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: n\n        type: int\n"
            "  - name: Node\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: snapshot\n        type: Snapshot\n"
        )
        ast.parse(src)
        assert "snapshot=make_valid_snapshot()," in src

    def test_self_referential_required_field_falls_back_to_none_with_comment(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Node\n    kind: frozen_dataclass\n"
            "    fields:\n"
            "      - name: value\n        type: int\n"
            "      - name: current\n        type: Node\n"
        )
        ast.parse(src)
        assert "current=None,  # override required: Node" in src
        assert "make_valid_node()," not in src.split("def make_valid_node")[1]

    def test_mutually_recursive_required_fields_fall_back_to_none(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: A\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: b\n        type: B\n"
            "  - name: B\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: a\n        type: A\n"
        )
        ast.parse(src)
        assert "b=None,  # override required: B" in src
        assert "a=None,  # override required: A" in src

    def test_optional_self_reference_resolves_to_none_not_flagged_as_cycle(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Node\n    kind: frozen_dataclass\n"
            "    fields:\n"
            "      - name: value\n        type: int\n"
            "      - name: parent\n        type: \"Node | None\"\n"
        )
        ast.parse(src)
        assert "parent=None," in src
        assert "override required" not in src

    def test_unrecognized_type_falls_back_to_none_with_comment(self):
        src = _scaffold(
            "module: m\npublic_api:\n"
            "  - name: Thing\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: handler\n        type: SomeExternalType\n"
        )
        assert "handler=None,  # override required: SomeExternalType" in src


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
