"""Tests for ModuleArchitect.generate_module_contract's `contract_yaml`
parameter (issue #57 follow-up): a formal `.contract.yml`, when given, must
reach the LLM prompt as the authoritative interface -- not just the
one-line `requirement` summary -- for both the plain and context-aware
prompt paths.
"""
from unittest.mock import MagicMock

from src.contracts.module_architect import CodebaseContext, ModuleArchitect

_VALID_JSON = (
    '{"module": {"id": "m", "name": "observation", "description": "d", "complexity": 2,'
    '"shared_state": "",'
    '"functions": [{"name": "is_success", "signature": "(self) -> bool", "docstring": "d"}],'
    '"integration_tests": []}}'
)


def _architect():
    llm = MagicMock()
    llm.generate.return_value = {"content": _VALID_JSON}
    return ModuleArchitect(llm_client=llm, model_id="test")


class TestContractYamlInjection:
    def test_no_contract_yaml_means_no_authoritative_block(self):
        arch = _architect()
        arch.generate_module_contract("build the observation module")
        prompt = arch._llm.generate.call_args[0][0]
        assert "AUTHORITATIVE CONTRACT" not in prompt

    def test_contract_yaml_is_injected_verbatim_in_the_plain_prompt(self):
        arch = _architect()
        contract_yaml = "module: observation\ndepends_on: []\n"
        arch.generate_module_contract(
            "build the observation module", contract_yaml=contract_yaml
        )
        prompt = arch._llm.generate.call_args[0][0]
        assert "AUTHORITATIVE CONTRACT" in prompt
        assert contract_yaml in prompt

    def test_contract_yaml_is_injected_in_the_context_aware_prompt(self):
        arch = _architect()
        contract_yaml = "module: observation\ndepends_on: [discovery_tree]\n"
        context = CodebaseContext(existing_functions=[])
        arch.generate_module_contract(
            "build the observation module", context=context, contract_yaml=contract_yaml
        )
        prompt = arch._llm.generate.call_args[0][0]
        assert "AUTHORITATIVE CONTRACT" in prompt
        assert contract_yaml in prompt

    def test_contract_yaml_with_braces_does_not_break_prompt_formatting(self):
        # dict[str, Node] / GridPlan(branch_count=W, ...) -- realistic YAML
        # content containing literal braces/parens must survive untouched.
        arch = _architect()
        contract_yaml = "module: replay_env\nnotes: >\n  nodes: dict[str, Node] = {}\n"
        result = arch.generate_module_contract(
            "build the replay_env module", contract_yaml=contract_yaml
        )
        assert result.success is True
        prompt = arch._llm.generate.call_args[0][0]
        assert "dict[str, Node] = {}" in prompt
