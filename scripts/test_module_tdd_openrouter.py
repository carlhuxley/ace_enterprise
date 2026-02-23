#!/usr/bin/env python3
"""Test module-level TDD flow with OpenRouter free models.

This tests the complete flow using OpenRouter's free tier:
1. Architect designs ModuleContract (with integration tests)
2. TDD Builder implements each function iteratively
3. Integration tests validate the complete module

Run: python scripts/test_module_tdd_openrouter.py
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
    """Run the module-level TDD flow with OpenRouter free models."""
    print("=" * 70)
    print("MODULE TDD FLOW (OpenRouter Free Models)")
    print("=" * 70)
    print(f"\nRequirement: {requirement}\n")

    audit = LocalAuditClient(AUDIT_DB_URL)
    session_id = f"module-tdd-openrouter-{int(time.time())}"

    # Phase 1: Generate module contract with integration tests
    # Use a capable free model for architecture (needs good reasoning)
    print("-" * 70)
    print("PHASE 1: MODULE ARCHITECT")
    print("-" * 70)

    # Try capable free models for architect role
    architect_models = [
        ("Llama 3.3 70B", "meta-llama/llama-3.3-70b-instruct:free"),
        ("DeepSeek R1", "deepseek/deepseek-r1-0528:free"),
        ("Qwen3 Coder", "qwen/qwen3-coder:free"),
        ("Auto (free)", "openrouter/free"),
    ]

    contract = None
    architect_model_used = None

    for name, model in architect_models:
        print(f"\nTrying {name} for architecture...")
        try:
            architect_llm = LLMClient(provider="openrouter", model=model)

            architect = ModuleArchitect(
                llm_client=architect_llm,
                audit_client=audit,
                model_id=f"openrouter-{model}",
            )

            result = architect.generate_module_contract(requirement, session_id=session_id)

            if result.success:
                contract = result.contract
                architect_model_used = name
                print(f"  SUCCESS in {result.elapsed_seconds:.2f}s")
                break
            else:
                print(f"  FAILED: {result.error}")

        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    if not contract:
        print("\nERROR: All architect models failed")
        return

    print(f"\nArchitect: {architect_model_used}")
    print(f"Module: {contract.name}")
    print(f"Complexity: {contract.complexity}")
    print(f"Shared state: {contract.shared_state}")
    print(f"\nFunctions ({len(contract.functions)}):")
    for f in contract.functions:
        print(f"  - {f.name}{f.signature}")

    print(f"\nIntegration tests ({len(contract.integration_tests)}):")
    for t in contract.integration_tests:
        print(f"  - {t.name}: {len(t.steps)} steps")

    # Phase 2: TDD Builder - implement each function
    print()
    print("-" * 70)
    print("PHASE 2: TDD BUILDER (per-function implementation)")
    print("-" * 70)

    # Use tiered approach with free models: start small, escalate
    builder_tiers = [
        ("Gemma 3 4B", "google/gemma-3-4b-it:free", "tiny"),
        ("Qwen3 4B", "qwen/qwen3-4b:free", "small"),
        ("Gemma 3 27B", "google/gemma-3-27b-it:free", "medium"),
        ("Llama 3.3 70B", "meta-llama/llama-3.3-70b-instruct:free", "large"),
        ("Auto (free)", "openrouter/free", "auto"),
    ]

    build_result = None
    builder_model_used = None

    for name, model, tier in builder_tiers:
        print(f"\nTrying {name} ({tier})...")

        try:
            builder_llm = LLMClient(provider="openrouter", model=model)

            builder = ModuleTDDBuilder(
                llm_client=builder_llm,
                audit_client=audit,
                model_id=f"openrouter-{model}",
                max_attempts_per_function=2,
            )

            build_result = builder.build_module(contract, session_id=session_id)

            print(f"\nFunction build results:")
            for fr in build_result.function_results:
                status = "PASS" if fr.success else "FAIL"
                model_info = f" [{fr.actual_model}]" if fr.actual_model else ""
                print(f"  {fr.function_name}: {status} ({fr.tdd_cycles} cycles){model_info}")

            if build_result.success:
                builder_model_used = name
                print(f"\nIntegration test results:")
                for test_name, passed in build_result.integration_test_results.items():
                    status = "PASS" if passed else "FAIL"
                    print(f"  {test_name}: {status}")
                break
            else:
                print(f"\nBuild failed: {build_result.error}")
                print("Escalating to next tier...")

        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(f"\nArchitect model: {architect_model_used}")
    print(f"Builder model: {builder_model_used or 'NONE (all failed)'}")

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
