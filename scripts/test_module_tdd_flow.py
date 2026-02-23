#!/usr/bin/env python3
"""Test module-level TDD flow with integration tests.

This tests the complete flow:
1. Architect designs ModuleContract (with integration tests)
2. TDD Builder implements each function iteratively
3. Integration tests validate the complete module

Run: python scripts/test_module_tdd_flow.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.audit.local_client import LocalAuditClient
from src.broker.module_architect import ModuleArchitect
from src.broker.module_tdd_builder import ModuleTDDBuilder
from src.utils.llm_client import LLMClient


AUDIT_DB_URL = "sqlite:///.local/audit.db"


def run_module_tdd_flow(requirement: str):
    """Run the module-level TDD flow with integration tests."""
    print("=" * 70)
    print("MODULE TDD FLOW (Architect → TDD Builder → Integration Tests)")
    print("=" * 70)
    print(f"\nRequirement: {requirement}\n")

    audit = LocalAuditClient(AUDIT_DB_URL)
    session_id = f"module-tdd-{int(time.time())}"

    # Phase 1: Generate module contract with integration tests
    print("-" * 70)
    print("PHASE 1: MODULE ARCHITECT (Llama 3.3 70B)")
    print("-" * 70)

    architect_llm = LLMClient(
        provider="togetherai",
        model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        base_url="https://api.together.xyz/v1",
    )

    architect = ModuleArchitect(
        llm_client=architect_llm,
        audit_client=audit,
        model_id="togetherai-Llama-3.3-70B",
    )

    result = architect.generate_module_contract(requirement, session_id=session_id)

    if not result.success:
        print(f"ERROR: Module contract generation failed: {result.error}")
        return

    contract = result.contract
    print(f"Generated module contract in {result.elapsed_seconds:.2f}s")
    print(f"\nModule: {contract.name}")
    print(f"Complexity: {contract.complexity}")
    print(f"Shared state: {contract.shared_state}")
    print(f"\nFunctions ({len(contract.functions)}):")
    for f in contract.functions:
        print(f"  - {f.name}{f.signature}")

    print(f"\nIntegration tests ({len(contract.integration_tests)}):")
    for t in contract.integration_tests:
        print(f"  - {t.name}: {len(t.steps)} steps")
        print(f"      Assert: {t.assertion}")

    # Phase 2: TDD Builder - implement each function
    print()
    print("-" * 70)
    print("PHASE 2: TDD BUILDER (per-function implementation)")
    print("-" * 70)

    # Use tiered approach: start cheap, escalate on failure
    builder_tiers = [
        ("Qwen 7B", "togetherai", "Qwen/Qwen2.5-7B-Instruct-Turbo", "low"),
        ("Llama 70B", "togetherai", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "high"),
    ]

    build_result = None

    for name, provider, model, cost in builder_tiers:
        print(f"\nTrying {name} ({cost} cost)...")

        builder_llm = LLMClient(
            provider=provider,
            model=model,
            base_url="https://api.together.xyz/v1",
        )

        builder = ModuleTDDBuilder(
            llm_client=builder_llm,
            audit_client=audit,
            model_id=f"{provider}-{model.split('/')[-1]}",
            max_attempts_per_function=2,
        )

        build_result = builder.build_module(contract, session_id=session_id)

        print(f"\nFunction build results:")
        for fr in build_result.function_results:
            status = "PASS" if fr.success else "FAIL"
            print(f"  {fr.function_name}: {status} ({fr.tdd_cycles} cycles)")

        if build_result.success:
            print(f"\nIntegration test results:")
            for test_name, passed in build_result.integration_test_results.items():
                status = "PASS" if passed else "FAIL"
                print(f"  {test_name}: {status}")
            break
        else:
            print(f"\nBuild failed: {build_result.error}")
            print("Escalating to next tier...")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if build_result:
        print(f"\nSuccess: {build_result.success}")
        print(f"Total TDD cycles: {build_result.total_cycles}")
        print(f"Elapsed time: {build_result.elapsed_seconds:.2f}s")

        if build_result.success:
            print(f"\nGenerated module ({len(build_result.module_code)} chars):")
            print("-" * 40)
            print(build_result.module_code)

    print(f"\nSession ID: {session_id}")


if __name__ == "__main__":
    requirement = """
    Build a simple counter module with:
    - increment() - adds 1 to counter
    - decrement() - subtracts 1 from counter (min 0)
    - get_count() - returns current count
    - reset() - sets counter to 0
    """

    if len(sys.argv) > 1:
        requirement = " ".join(sys.argv[1:])

    run_module_tdd_flow(requirement)
