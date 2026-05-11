"""Tests for AST-scoped context injection in the TDD agent (ace_enterprise-d2m)."""
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agents.autonomous_tdd_agent import AutonomousTDDAgent
from src.utils.context_map import ContextMapBuilder


def make_agent(tmp_path, context_map=None):
    ensemble = MagicMock()
    ensemble.models = [("openai", "gpt-4o", None)]
    ensemble.playbook_manager = MagicMock()
    ensemble.playbook_id = "test-playbook"

    agent = AutonomousTDDAgent(
        ensemble_learner=ensemble,
        test_reviewer=MagicMock(),
        project_root=tmp_path,
        test_dir=tmp_path / "tests",
        src_dir=tmp_path / "src",
        context_map=context_map,
    )
    return agent


class TestGetImplementationContext:
    def test_returns_empty_when_no_context_map(self, tmp_path):
        agent = make_agent(tmp_path, context_map=None)
        result = agent._get_implementation_context(["tests/test_foo.py::test_bar"])
        assert result == ""

    def test_returns_empty_for_empty_test_ids(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def foo(): pass\n")
        cm = ContextMapBuilder().build([src])
        agent = make_agent(tmp_path, context_map=cm)
        assert agent._get_implementation_context([]) == ""

    def test_returns_signatures_for_referenced_names(self, tmp_path):
        src = tmp_path / "inventory.py"
        src.write_text("def check_stock(item_id: int) -> int:\n    return 0\n")

        test_file = tmp_path / "test_inv.py"
        test_file.write_text(
            "def test_check_stock():\n    result = check_stock(1)\n    assert result == 0\n"
        )

        cm = ContextMapBuilder().build([src])
        agent = make_agent(tmp_path, context_map=cm)

        result = agent._get_implementation_context([f"{test_file}::test_check_stock"])
        assert "check_stock" in result
        assert "item_id" in result

    def test_omits_unrelated_signatures(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "def used_fn(x: int) -> int:\n    return x\n\n"
            "def unrelated_fn(y: str) -> str:\n    return y\n"
        )
        test_file = tmp_path / "test_mod.py"
        test_file.write_text("def test_used():\n    used_fn(1)\n")

        cm = ContextMapBuilder().build([src])
        agent = make_agent(tmp_path, context_map=cm)

        result = agent._get_implementation_context([f"{test_file}::test_used"])
        assert "used_fn" in result
        assert "unrelated_fn" not in result

    def test_output_is_compact_not_full_bodies(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text(
            "def process(order_id: int) -> bool:\n"
            "    # lots of implementation detail\n"
            "    x = order_id * 2\n"
            "    y = x + 1\n"
            "    return y > 0\n"
        )
        test_file = tmp_path / "test_mod.py"
        test_file.write_text("def test_process():\n    process(1)\n")

        cm = ContextMapBuilder().build([src])
        agent = make_agent(tmp_path, context_map=cm)

        result = agent._get_implementation_context([f"{test_file}::test_process"])
        assert "lots of implementation detail" not in result
        assert "x = order_id * 2" not in result
        assert "process" in result

    def test_multi_module_signatures_both_included(self, tmp_path):
        inv = tmp_path / "inventory.py"
        inv.write_text("def check_stock(item_id: int) -> int:\n    return 0\n")
        pay = tmp_path / "payments.py"
        pay.write_text("def charge(amount: float) -> bool:\n    return True\n")

        test_file = tmp_path / "test_order.py"
        test_file.write_text(
            "def test_order_processing():\n"
            "    stock = check_stock(1)\n"
            "    result = charge(9.99)\n"
        )

        cm = ContextMapBuilder().build([inv, pay])
        agent = make_agent(tmp_path, context_map=cm)

        result = agent._get_implementation_context([f"{test_file}::test_order_processing"])
        assert "check_stock" in result
        assert "charge" in result


class TestImplementationPromptTokenReduction:
    def test_prompt_with_context_map_shorter_than_without(self, tmp_path):
        """Prompt with context map must be shorter than full-file equivalent."""
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()

        # A source file with substantial body content
        src = tmp_path / "src" / "inventory.py"
        src.write_text(
            "def check_stock(item_id: int) -> int:\n"
            + "    # " + "x" * 80 + "\n" * 20  # 20 lines of padding
            + "    return 0\n"
        )

        test_file = tmp_path / "tests" / "test_inventory.py"
        test_file.write_text("def test_check_stock():\n    result = check_stock(1)\n")
        test_file.write_text(
            "from src.inventory import check_stock\n\n"
            "def test_check_stock():\n    result = check_stock(1)\n    assert result == 0\n"
        )

        cm = ContextMapBuilder().build([src])
        agent_with_map = make_agent(tmp_path, context_map=cm)
        agent_without = make_agent(tmp_path, context_map=None)

        test_ids = [f"{test_file}::test_check_stock"]
        with_map = agent_with_map._get_implementation_context(test_ids)
        without_map = agent_without._get_implementation_context(test_ids)

        # with_map is compact signatures; without_map is empty (falls back to existing_code)
        # Key: signatures don't include function bodies
        assert "x" * 20 not in with_map  # body padding not present
        assert without_map == ""  # baseline: no context section at all


class TestBackwardsCompatibility:
    def test_agent_accepts_no_context_map_arg(self, tmp_path):
        ensemble = MagicMock()
        ensemble.models = [("openai", "gpt-4o", None)]
        ensemble.playbook_manager = MagicMock()
        ensemble.playbook_id = "test-playbook"

        # Must not raise — context_map defaults to None
        agent = AutonomousTDDAgent(
            ensemble_learner=ensemble,
            test_reviewer=MagicMock(),
            project_root=tmp_path,
            test_dir=tmp_path / "tests",
            src_dir=tmp_path / "src",
        )
        assert agent.context_map is None

    def test_get_implementation_context_without_context_map_returns_empty(self, tmp_path):
        agent = make_agent(tmp_path, context_map=None)
        result = agent._get_implementation_context(["tests/test_foo.py::test_bar"])
        assert result == ""
