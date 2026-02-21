#!/usr/bin/env python3
"""Test the full AutonomousTDDAgent with effGen local model.

This integrates:
- AutonomousTDDAgent (full TDD cycle)
- EffGenClient (local model adapter)
- Playbook retrieval (pattern injection)
- Audit trail (event logging)

Bead: ace_enterprise-41e

Run from ace_enterprise root:
    python scripts/test_tdd_agent_effgen.py
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.effgen_client import EffGenClient


def test_effgen_client():
    """Test that EffGenClient works with the LLMClient interface."""
    print("=" * 70)
    print("TEST 1: EffGenClient Interface")
    print("=" * 70)

    client = EffGenClient(
        model="Qwen/Qwen2.5-1.5B-Instruct",
        quantization="4bit",
    )

    print(f"\nClient initialized:")
    print(f"  Model: {client.model}")
    print(f"  Provider: {client.provider}")
    print(f"  Quantization: {client.quantization}")

    # Test generate
    print("\nTesting generate()...")
    result = client.generate(
        prompt="Write a Python function that returns the square of a number. Just the function, no explanation.",
        system_prompt="You are a Python coding assistant. Output only code.",
        max_tokens=100,
    )

    print(f"\nResult:")
    print(f"  Content: {result['content'][:200]}...")
    print(f"  Tokens: {result['tokens_used']}")
    print(f"  Latency: {result['latency_ms']}ms")
    print(f"  Model: {result['model']}")

    # Validate interface
    assert "content" in result
    assert "tokens_used" in result
    assert "latency_ms" in result
    assert "model" in result

    print("\n✓ EffGenClient implements LLMClient interface correctly")
    return True


def test_effgen_with_tdd_agent():
    """Test EffGenClient with the TDD agent (mocked ensemble)."""
    print("\n" + "=" * 70)
    print("TEST 2: EffGenClient with TDD Agent")
    print("=" * 70)

    from src.agents.autonomous_tdd_agent import AutonomousTDDAgent

    # Create effGen client
    effgen_client = EffGenClient(
        model="Qwen/Qwen2.5-1.5B-Instruct",
        quantization="4bit",
    )

    # Mock the ensemble learner (which normally uses external APIs)
    mock_ensemble = MagicMock()
    mock_ensemble.models = [("effgen", "Qwen/Qwen2.5-1.5B-Instruct", None)]
    mock_ensemble.playbook_manager = MagicMock()
    mock_ensemble.playbook_id = "test-playbook"

    # Mock test reviewer
    mock_reviewer = MagicMock()
    mock_reviewer.review.return_value = MagicMock(
        quality_score=0.9,
        issues=[],
        suggestions=[],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        test_dir = project_root / "tests"
        src_dir = project_root / "src"
        test_dir.mkdir()
        src_dir.mkdir()

        # Patch LLMClient to use our EffGenClient
        with patch("src.agents.autonomous_tdd_agent.LLMClient") as MockLLMClient:
            # Make LLMClient return our effgen client
            MockLLMClient.return_value = effgen_client

            with patch("src.playbook.retrieval.BulletRetriever"):
                agent = AutonomousTDDAgent(
                    ensemble_learner=mock_ensemble,
                    test_reviewer=mock_reviewer,
                    project_root=project_root,
                    test_dir=test_dir,
                    src_dir=src_dir,
                )

        print(f"\nTDD Agent initialized:")
        print(f"  Project: {project_root}")
        print(f"  Test dir: {test_dir}")
        print(f"  Src dir: {src_dir}")
        print(f"  LLM Client: {type(agent.llm_client)}")

        # Verify the agent has our client
        assert agent.llm_client == effgen_client
        print("\n✓ TDD Agent using EffGenClient")

    return True


def test_full_tdd_cycle_with_effgen():
    """Run a simple TDD cycle using EffGenClient."""
    print("\n" + "=" * 70)
    print("TEST 3: Full TDD Cycle with EffGen")
    print("=" * 70)

    from src.utils.effgen_client import EffGenClient
    from src.audit.local_client import LocalAuditClient
    from src.audit.schemas import AuditEventType

    client = EffGenClient()
    audit = LocalAuditClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)
        test_file = work_dir / "test_square.py"
        impl_file = work_dir / "square.py"

        # RED: Write failing test
        print("\n[RED] Writing test...")
        test_prompt = """Write a pytest test for a function called 'square' that takes a number and returns its square.
The test should check: square(2) == 4, square(0) == 0, square(-3) == 9.
Output only the test code, no explanations."""

        test_result = client.generate(test_prompt)
        test_code = test_result["content"]

        # Clean up code
        if "```python" in test_code:
            test_code = test_code.split("```python")[1].split("```")[0]
        test_code = test_code.strip()

        # Ensure import
        if "import pytest" not in test_code:
            test_code = "import pytest\nfrom square import square\n\n" + test_code
        if "from square import" not in test_code:
            test_code = "from square import square\n" + test_code

        test_file.write_text(test_code)
        print(f"  Test code:\n{test_code[:300]}...")

        # Audit: TEST_GENERATED
        audit.emit_simple(
            event_type=AuditEventType.TEST_GENERATED,
            actor_id="tdd-agent-effgen",
            payload={"phase": "RED", "test_file": str(test_file)},
        )

        # GREEN: Write implementation
        print("\n[GREEN] Writing implementation...")
        impl_prompt = """Write a Python function called 'square' that takes a number and returns its square.
Output only the function, no explanations."""

        impl_result = client.generate(impl_prompt)
        impl_code = impl_result["content"]

        if "```python" in impl_code:
            impl_code = impl_code.split("```python")[1].split("```")[0]
        impl_code = impl_code.strip()

        impl_file.write_text(impl_code)
        print(f"  Implementation:\n{impl_code}")

        # Audit: IMPLEMENTATION_GENERATED
        audit.emit_simple(
            event_type=AuditEventType.IMPLEMENTATION_GENERATED,
            actor_id="tdd-agent-effgen",
            payload={"phase": "GREEN", "impl_file": str(impl_file)},
        )

        # Run tests
        print("\n[VALIDATE] Running pytest...")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", str(test_file)],
            capture_output=True,
            text=True,
            cwd=str(work_dir),
            env={**subprocess.os.environ, "PYTHONPATH": str(work_dir)},
        )

        passed = result.returncode == 0
        print(f"  Result: {'PASSED' if passed else 'FAILED'}")
        if not passed:
            print(f"  Output: {result.stdout[:500]}")
            print(f"  Errors: {result.stderr[:500]}")

        # Audit: CYCLE_COMPLETED
        audit.emit_simple(
            event_type=AuditEventType.CYCLE_COMPLETED,
            actor_id="tdd-agent-effgen",
            payload={
                "success": passed,
                "test_file": str(test_file),
                "impl_file": str(impl_file),
            },
        )

        print(f"\n{'✓' if passed else '✗'} TDD Cycle {'completed successfully' if passed else 'failed'}")

        # Show audit stats
        stats = audit.get_stats()
        print(f"\nAudit events recorded: {stats['total_events']}")

        return passed


def main():
    print("=" * 70)
    print("FULL TDD AGENT + EFFGEN INTEGRATION TEST")
    print("=" * 70)
    print("\nThis test validates:")
    print("  1. EffGenClient implements LLMClient interface")
    print("  2. TDD Agent can use EffGenClient")
    print("  3. Full TDD cycle works with local model")

    results = []

    # Test 1: Client interface
    try:
        results.append(("EffGenClient Interface", test_effgen_client()))
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        results.append(("EffGenClient Interface", False))

    # Test 2: TDD Agent integration
    try:
        results.append(("TDD Agent Integration", test_effgen_with_tdd_agent()))
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        results.append(("TDD Agent Integration", False))

    # Test 3: Full TDD cycle
    try:
        results.append(("Full TDD Cycle", test_full_tdd_cycle_with_effgen()))
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Full TDD Cycle", False))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")

    all_passed = all(r[1] for r in results)
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
