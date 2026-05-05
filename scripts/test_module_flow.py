#!/usr/bin/env python3
"""Test module-level contract flow for stateful systems.

This tests the module architect approach where:
1. All functions are generated together
2. Shared state is explicit
3. Integration tests exercise the full module

Run: python scripts/test_module_flow.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.contracts.module_architect import (
    ModuleArchitect,
    generate_module_prompt,
    validate_module,
)
from src.utils.llm_client import LLMClient


AUDIT_DB_URL = "sqlite:///.local/audit.db"


def run_module_flow(requirement: str):
    """Run the module-level contract flow."""
    print("=" * 70)
    print("MODULE-LEVEL CONTRACT FLOW (for stateful systems)")
    print("=" * 70)
    print(f"\nRequirement: {requirement}\n")

    audit = LocalAuditClient(AUDIT_DB_URL)
    session_id = f"module-flow-{int(time.time())}"

    # Phase 1: Generate module contract
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

    # Phase 2: Generate implementation
    print()
    print("-" * 70)
    print("PHASE 2: MODULE BUILDER")
    print("-" * 70)

    prompt = generate_module_prompt(contract)
    print("Prompt preview:")
    print(prompt[:500] + "..." if len(prompt) > 500 else prompt)
    print()

    # Try with escalation
    builders = [
        ("Qwen 7B", "togetherai", "Qwen/Qwen2.5-7B-Instruct-Turbo"),
        ("Llama 70B", "togetherai", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    ]

    success = False
    final_code = None
    attempts_total = 0

    for name, provider, model in builders:
        print(f"\nTrying {name}...")

        builder_llm = LLMClient(
            provider=provider,
            model=model,
            base_url="https://api.together.xyz/v1",
        )

        for attempt in range(2):
            attempts_total += 1
            print(f"  Attempt {attempt + 1}...", end=" ", flush=True)

            start = time.time()
            llm_result = builder_llm.generate(prompt)
            code = llm_result["content"]

            # Extract code
            if "```python" in code:
                code = code.split("```python")[1]
                if "```" in code:
                    code = code.split("```")[0]
            elif "```" in code:
                code = code.split("```")[1]
                if "```" in code:
                    code = code.split("```")[0]

            elapsed = time.time() - start

            # Validate
            passed, failures = validate_module(contract, code)

            if passed:
                print(f"PASSED ({elapsed:.1f}s)")
                success = True
                final_code = code

                # Audit success
                audit.emit_simple(
                    event_type=AuditEventType.CYCLE_COMPLETED,
                    actor_id=f"{provider}-{model.split('/')[-1]}",
                    payload={
                        "contract_id": contract.id,
                        "contract_type": "module",
                        "complexity": contract.complexity,
                        "attempts": attempt + 1,
                        "success": True,
                    },
                    session_id=session_id,
                )
                break
            else:
                print(f"FAILED ({elapsed:.1f}s)")
                for f in failures[:3]:
                    print(f"    - {f}")

                # Audit failure
                audit.emit_simple(
                    event_type=AuditEventType.CYCLE_COMPLETED,
                    actor_id=f"{provider}-{model.split('/')[-1]}",
                    payload={
                        "contract_id": contract.id,
                        "contract_type": "module",
                        "complexity": contract.complexity,
                        "attempts": attempt + 1,
                        "success": False,
                        "failure_count": len(failures),
                    },
                    session_id=session_id,
                )

        if success:
            break
        else:
            print(f"  Escalating to next model...")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\nSuccess: {success}")
    print(f"Total attempts: {attempts_total}")

    if success and final_code:
        print(f"\nGenerated code ({len(final_code)} chars):")
        print("-" * 40)
        print(final_code[:1000] + "..." if len(final_code) > 1000 else final_code)

    print(f"\nSession ID: {session_id}")


if __name__ == "__main__":
    requirement = """
    Build a simple inventory management system with:
    - add_item(name, quantity, price) - adds item to inventory
    - get_item(name) - returns item details or None
    - update_quantity(name, delta) - adjusts quantity by delta
    - get_total_value() - returns sum of (quantity * price) for all items
    - get_low_stock(threshold) - returns list of items below threshold
    """

    if len(sys.argv) > 1:
        requirement = " ".join(sys.argv[1:])

    run_module_flow(requirement)
