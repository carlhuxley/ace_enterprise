"""Tests for src/contracts/module_contract_features.py."""

from src.contracts.module_contract_features import synthesize_feature_from_contract
from src.contracts.module_contract_schema import ContractDocument


def _doc(yaml_text: str) -> ContractDocument:
    return ContractDocument.from_yaml(yaml_text)


class TestNoScenarioKinds:
    def test_constant_gets_no_scenario(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: MAX\n    kind: constant\n    type: int\n    value: \"5\"\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        assert len(feature.scenarios) == 1
        assert feature.scenarios[0].name == "m imports cleanly"

    def test_type_alias_gets_no_scenario(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Handler\n    kind: type_alias\n    definition: \"Callable[[int], None]\"\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        assert feature.scenarios[0].name == "m imports cleanly"

    def test_protocol_gets_no_scenario(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Thing\n    kind: protocol\n"
            "    methods:\n      - name: run\n        signature: \"run(self) -> None\"\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        assert feature.scenarios[0].name == "m imports cleanly"

    def test_abc_gets_no_scenario(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Base\n    kind: abc\n"
            "    methods:\n      - name: run\n        signature: \"run(self) -> None\"\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        assert feature.scenarios[0].name == "m imports cleanly"


class TestDataclassScenarios:
    def test_plain_dataclass_no_methods_no_raises_gets_no_scenario(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Point\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: x\n        type: int\n"
            "  - name: greet\n    kind: function\n    signature: \"(name: str) -> str\"\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        assert [s.name for s in feature.scenarios] == ["greet"]

    def test_dataclass_with_raises_gets_invariant_scenario(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Node\n    kind: mutable_dataclass\n"
            "    fields:\n      - name: score\n        type: \"float | None\"\n"
            "    raises:\n      - exception: ValueError\n        when: \"score is negative\"\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        assert len(feature.scenarios) == 1
        scenario = feature.scenarios[0]
        assert scenario.name == "Node enforces its invariants"
        assert any("make_valid_node(**overrides)" in s and "NOT a pytest fixture" in s for s in scenario.steps)
        assert any("ValueError is raised when score is negative" in s for s in scenario.steps)

    def test_dataclass_with_its_own_methods_gets_one_scenario_per_method(self):
        """The exact real-world gap this closes: a dataclass-kind entry
        (e.g. discovery_tree's DiscoveryTree) can carry its own real methods
        (attach, children_of) that a dependent module can hallucinate as
        free functions (#73) if they're never exercised by a scenario."""
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Tree\n    kind: mutable_dataclass\n"
            "    fields:\n      - name: root_id\n        type: str\n"
            "    methods:\n"
            "      - name: attach\n        signature: \"attach(self, parent_id: str) -> Tree\"\n"
            "        returns: \"a NEW Tree instance\"\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        assert len(feature.scenarios) == 1
        scenario = feature.scenarios[0]
        assert scenario.name == "Tree.attach"
        assert any("make_valid_tree(**overrides)" in s and "NOT a pytest fixture" in s for s in scenario.steps)
        assert any("Tree.attach returns a NEW Tree instance" in s for s in scenario.steps)


class TestConcreteClassScenarios:
    def test_constructor_only_class_with_no_methods_still_gets_a_scenario(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Widget\n    kind: concrete_class\n"
            "    constructor:\n      params:\n        - name: size\n          type: int\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        assert len(feature.scenarios) == 1
        scenario = feature.scenarios[0]
        assert scenario.name == "Widget construction"
        assert any("size: int" in s for s in scenario.steps)
        assert any("Widget instance is created" in s for s in scenario.steps)

    def test_one_scenario_per_method(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Widget\n    kind: concrete_class\n"
            "    constructor:\n      params:\n        - name: size\n          type: int\n"
            "    methods:\n"
            "      - name: grow\n        signature: \"grow(self) -> None\"\n"
            "      - name: shrink\n        signature: \"shrink(self) -> None\"\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        assert [s.name for s in feature.scenarios] == ["Widget.grow", "Widget.shrink"]

    def test_method_returns_and_raises_produce_specific_steps(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Runner\n    kind: concrete_class\n"
            "    constructor:\n      params: []\n"
            "    methods:\n"
            "      - name: run_outer_loop\n"
            "        signature: \"run_outer_loop(self, max_iterations: int) -> Policy\"\n"
            "        returns: \"the final winning Policy\"\n"
            "        raises:\n"
            "          - exception: ValueError\n"
            "            when: \"max_iterations < 1\"\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        steps = feature.scenarios[0].steps
        assert "Then run_outer_loop.run_outer_loop returns the final winning Policy" not in steps
        assert any("Runner.run_outer_loop returns the final winning Policy" in s for s in steps)
        assert any("ValueError is raised when max_iterations < 1" in s for s in steps)

    def test_no_returns_preconditions_raises_or_semantics_falls_back_to_generic_step(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Widget\n    kind: concrete_class\n"
            "    constructor:\n      params: []\n"
            "    methods:\n      - name: run\n        signature: \"run(self) -> None\"\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        assert any("Widget.run behaves per its contract" in s for s in feature.scenarios[0].steps)


class TestFixtureFactoryAwareness:
    def test_dataclass_scenario_step_references_the_factory_not_raw_fields(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Node\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: value\n        type: int\n"
            "    methods:\n      - name: doubled\n        signature: \"doubled(self) -> int\"\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        steps = feature.scenarios[0].steps
        assert any("make_valid_node(**overrides)" in s for s in steps)
        assert not any("value: int" in s for s in steps)

    def test_dataclass_scenario_step_warns_the_factory_is_not_a_pytest_fixture(self):
        """#75: a real live run found the model sometimes writing
        `def test_x(make_valid_node):`, treating the factory as a pytest
        fixture to inject rather than a plain function to import and call."""
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Node\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: value\n        type: int\n"
            "    methods:\n      - name: doubled\n        signature: \"doubled(self) -> int\"\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        steps = feature.scenarios[0].steps
        assert any("NOT a pytest fixture" in s for s in steps)
        assert any("test function parameter" in s for s in steps)

    def test_concrete_class_scenario_step_is_unaffected_by_factories(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Widget\n    kind: concrete_class\n"
            "    constructor:\n      params:\n        - name: size\n          type: int\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        steps = feature.scenarios[0].steps
        assert any("constructed with size: int" in s for s in steps)
        assert not any("make_valid" in s for s in steps)

    def test_context_lists_available_fixture_factories(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Node\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: value\n        type: int\n"
            "  - name: Empty\n    kind: frozen_dataclass\n"
        )
        _, context = synthesize_feature_from_contract(doc)
        assert "Test fixture factories available: make_valid_node(**overrides)" in context
        assert "make_valid_empty" not in context

    def test_context_omits_fixture_factory_line_when_none_exist(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: greet\n    kind: function\n    signature: \"(name: str) -> str\"\n"
        )
        _, context = synthesize_feature_from_contract(doc)
        assert "fixture factories" not in context

    def test_context_warns_factories_are_not_pytest_fixtures(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: Node\n    kind: frozen_dataclass\n"
            "    fields:\n      - name: value\n        type: int\n"
        )
        _, context = synthesize_feature_from_contract(doc)
        assert "NOT pytest fixtures" in context
        assert "test function parameter" in context


class TestFunctionScenarios:
    def test_one_scenario_per_function_with_specific_steps(self):
        doc = _doc(
            "module: m\npublic_api:\n"
            "  - name: greet\n    kind: function\n    signature: \"(name: str) -> str\"\n"
            "    returns: \"a greeting string\"\n"
            "    preconditions: [\"name is non-empty\"]\n"
        )
        feature, _ = synthesize_feature_from_contract(doc)
        assert len(feature.scenarios) == 1
        scenario = feature.scenarios[0]
        assert scenario.name == "greet"
        assert "Given name is non-empty" in scenario.steps
        assert "Then greet returns a greeting string" in scenario.steps


class TestFallbackAndContext:
    def test_empty_public_api_gets_import_only_fallback(self):
        doc = _doc("module: m\n")
        feature, context = synthesize_feature_from_contract(doc)
        assert len(feature.scenarios) == 1
        assert feature.scenarios[0].name == "m imports cleanly"
        assert "Module: m" in context

    def test_context_includes_module_and_entry_descriptions(self):
        doc = _doc(
            "module: m\ndescription: does a thing\npublic_api:\n"
            "  - name: greet\n    kind: function\n    signature: \"(name: str) -> str\"\n"
            "    description: greets someone\n"
        )
        _, context = synthesize_feature_from_contract(doc)
        assert "Module: m" in context
        assert "does a thing" in context
        assert "greet: greets someone" in context
