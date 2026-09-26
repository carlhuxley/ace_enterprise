"""Tests for src/contracts/module_contract_schema.py."""

import pytest
from pydantic import ValidationError

from src.contracts.module_contract_schema import ContractDocument


def _doc(yaml_text: str) -> ContractDocument:
    return ContractDocument.from_yaml(yaml_text)


class TestTopLevel:
    def test_minimal_document_defaults(self):
        doc = _doc("module: foo\n")
        assert doc.module == "foo"
        assert doc.version == "0.1.0"
        assert doc.depends_on == []
        assert doc.public_api == []

    def test_full_document_fields(self):
        doc = _doc(
            "module: foo\n"
            "version: 1.2.3\n"
            "depends_on: [bar, baz]\n"
            "external_dependencies: [pydantic]\n"
            "description: does a thing\n"
            "invariants: [\"x always > 0\"]\n"
            "notes: extra module-level prose\n"
        )
        assert doc.depends_on == ["bar", "baz"]
        assert doc.external_dependencies == ["pydantic"]
        assert doc.invariants == ["x always > 0"]
        assert doc.notes == "extra module-level prose"


class TestFrozenAndMutableDataclass:
    def test_frozen_dataclass_with_fields(self):
        doc = _doc(
            "module: foo\n"
            "public_api:\n"
            "  - name: Point\n"
            "    kind: frozen_dataclass\n"
            "    fields:\n"
            "      - name: x\n"
            "        type: int\n"
            "      - name: y\n"
            "        type: int\n"
            "        default: \"0\"\n"
        )
        entry = doc.public_api[0]
        assert entry.kind == "frozen_dataclass"
        assert entry.impl == "dataclass"
        assert entry.fields[0].default is None
        assert entry.fields[1].default == "0"

    def test_pydantic_model_impl(self):
        doc = _doc(
            "module: foo\n"
            "public_api:\n"
            "  - name: Point\n"
            "    kind: frozen_dataclass\n"
            "    impl: pydantic_model\n"
            "    fields:\n"
            "      - name: x\n"
            "        type: int\n"
        )
        assert doc.public_api[0].impl == "pydantic_model"

    def test_field_without_default_after_defaulted_field_rejected_for_dataclass(self):
        with pytest.raises(ValidationError, match="invalid dataclass field order"):
            _doc(
                "module: foo\n"
                "public_api:\n"
                "  - name: Point\n"
                "    kind: frozen_dataclass\n"
                "    fields:\n"
                "      - name: x\n"
                "        type: int\n"
                "        default: \"0\"\n"
                "      - name: y\n"
                "        type: int\n"
            )

    def test_same_field_order_is_fine_for_pydantic_model(self):
        # Pydantic models don't go through stdlib dataclasses machinery, so
        # the ordering restriction above doesn't apply.
        doc = _doc(
            "module: foo\n"
            "public_api:\n"
            "  - name: Point\n"
            "    kind: frozen_dataclass\n"
            "    impl: pydantic_model\n"
            "    fields:\n"
            "      - name: x\n"
            "        type: int\n"
            "        default: \"0\"\n"
            "      - name: y\n"
            "        type: int\n"
        )
        assert len(doc.public_api[0].fields) == 2


class TestProtocolAndAbc:
    def test_protocol_with_property_shaped_method(self):
        doc = _doc(
            "module: foo\n"
            "public_api:\n"
            "  - name: Thing\n"
            "    kind: protocol\n"
            "    methods:\n"
            "      - name: value\n"
            "        property: true\n"
            "        signature: \"value -> int\"\n"
        )
        method = doc.public_api[0].methods[0]
        assert method.property is True

    def test_abc_requires_no_special_fields(self):
        doc = _doc(
            "module: foo\n"
            "public_api:\n"
            "  - name: Thing\n"
            "    kind: abc\n"
            "    methods:\n"
            "      - name: run\n"
            "        signature: \"run(self) -> None\"\n"
        )
        assert doc.public_api[0].kind == "abc"


class TestConcreteClass:
    def test_requires_constructor(self):
        with pytest.raises(ValidationError, match="requires 'constructor'"):
            _doc(
                "module: foo\n"
                "public_api:\n"
                "  - name: Thing\n"
                "    kind: concrete_class\n"
            )

    def test_constructor_params_parsed(self):
        doc = _doc(
            "module: foo\n"
            "public_api:\n"
            "  - name: Thing\n"
            "    kind: concrete_class\n"
            "    constructor:\n"
            "      params:\n"
            "        - name: x\n"
            "          type: int\n"
            "        - name: y\n"
            "          type: str\n"
            "          default: \"'a'\"\n"
        )
        params = doc.public_api[0].constructor.params
        assert [p.name for p in params] == ["x", "y"]
        assert params[1].default == "'a'"


class TestTypeAliasFunctionConstant:
    def test_type_alias_requires_definition(self):
        with pytest.raises(ValidationError, match="requires 'definition'"):
            _doc("module: foo\npublic_api:\n  - name: Thing\n    kind: type_alias\n")

    def test_function_requires_bare_signature(self):
        with pytest.raises(ValidationError, match="bare"):
            _doc(
                "module: foo\n"
                "public_api:\n"
                "  - name: greet\n"
                "    kind: function\n"
                "    signature: \"greet(name: str) -> str\"\n"
            )

    def test_function_bare_signature_accepted(self):
        doc = _doc(
            "module: foo\n"
            "public_api:\n"
            "  - name: greet\n"
            "    kind: function\n"
            "    signature: \"(name: str) -> str\"\n"
        )
        assert doc.public_api[0].signature == "(name: str) -> str"

    def test_constant_requires_value(self):
        with pytest.raises(ValidationError, match="requires 'value'"):
            _doc(
                "module: foo\n"
                "public_api:\n"
                "  - name: MAX\n"
                "    kind: constant\n"
                "    type: int\n"
            )
