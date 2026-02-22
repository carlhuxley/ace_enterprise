#!/usr/bin/env python3
"""Test the full architect → builder flow with audit tracking.

This script demonstrates:
1. Architect (Llama 3.3 70B) generates contracts from requirements
2. Contracts are routed based on complexity
3. Builder (smaller model) implements each contract
4. Full audit trail captures both phases

Run: python scripts/test_architect_flow.py
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.broker.contract_architect import ContractArchitect, create_architect_from_config
from src.broker.contract_driven import ContractValidator
from src.utils.llm_client import LLMClient


# Configuration
ARCHITECT_PROVIDER = "togetherai"
ARCHITECT_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
ARCHITECT_BASE_URL = "https://api.together.xyz/v1"

BUILDER_PROVIDER = "togetherai"
BUILDER_MODEL = "Qwen/Qwen2.5-7B-Instruct-Turbo"  # Smaller model for implementation
BUILDER_BASE_URL = "https://api.together.xyz/v1"

AUDIT_DB_URL = "sqlite:///.local/audit.db"


def run_full_flow(requirement: str):
    """Run the full architect → builder flow."""
    print("=" * 70)
    print("CONTRACT-DRIVEN TDD: ARCHITECT → BUILDER FLOW")
    print("=" * 70)
    print(f"\nRequirement: {requirement}\n")

    # Initialize audit
    audit = LocalAuditClient(AUDIT_DB_URL)
    session_id = f"architect-flow-{int(time.time())}"

    # Phase 1: Architect generates contracts
    print("-" * 70)
    print("PHASE 1: ARCHITECT (Llama 3.3 70B)")
    print("-" * 70)

    architect = create_architect_from_config(
        provider=ARCHITECT_PROVIDER,
        model=ARCHITECT_MODEL,
        base_url=ARCHITECT_BASE_URL,
        audit_db_url=AUDIT_DB_URL,
    )

    arch_result = architect.generate_contracts(requirement, session_id=session_id)

    if not arch_result.success:
        print(f"ERROR: Contract generation failed: {arch_result.error}")
        return

    print(f"Generated {len(arch_result.contracts)} contracts in {arch_result.elapsed_seconds:.2f}s")
    print()

    for contract in arch_result.contracts:
        print(f"  [{contract.id}] {contract.function_name}")
        print(f"      Signature: {contract.signature}")
        print(f"      Complexity: {contract.complexity}")
        print(f"      Tests: {len(contract.test_cases)}")
        print()

    # Phase 2: Builder implements contracts
    print("-" * 70)
    print("PHASE 2: BUILDER (Smaller Model)")
    print("-" * 70)

    builder_llm = LLMClient(
        provider=BUILDER_PROVIDER,
        model=BUILDER_MODEL,
        base_url=BUILDER_BASE_URL,
    )
    validator = ContractValidator()
    builder_id = f"{BUILDER_PROVIDER}-{BUILDER_MODEL.split('/')[-1]}"

    results = []
    for contract in arch_result.contracts:
        print(f"\nImplementing: {contract.function_name} (complexity {contract.complexity})")

        interface = contract.to_interface_contract()
        prompt = interface.to_prompt()

        start_time = time.time()
        success = False
        attempts = 0
        max_attempts = 3

        for attempt in range(max_attempts):
            attempts = attempt + 1
            print(f"  Attempt {attempts}...", end=" ")

            # Generate implementation
            llm_result = builder_llm.generate(prompt)
            code = llm_result["content"]

            # Extract function code
            if "def " in code:
                code = code[code.index("def "):]
                if "```" in code:
                    code = code[:code.index("```")]

            # Validate
            impl = validator.validate(interface, code)

            if impl.status.value == "validated":
                print("PASSED")
                success = True
                break
            else:
                print(f"FAILED - {impl.error or 'tests failed'}")

        elapsed = time.time() - start_time

        # Audit: CYCLE_COMPLETED
        audit.emit_simple(
            event_type=AuditEventType.CYCLE_COMPLETED,
            actor_id=builder_id,
            payload={
                "contract_id": contract.id,
                "function_name": contract.function_name,
                "complexity": contract.complexity,
                "attempts": attempts,
                "elapsed_seconds": elapsed,
                "success": success,
                "architect_model": arch_result.architect_model,
            },
            session_id=session_id,
        )

        results.append({
            "contract_id": contract.id,
            "function_name": contract.function_name,
            "complexity": contract.complexity,
            "success": success,
            "attempts": attempts,
            "elapsed": elapsed,
        })

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    success_count = sum(1 for r in results if r["success"])
    print(f"\nContracts: {len(results)}")
    print(f"Successful: {success_count}/{len(results)}")

    print("\nBy complexity:")
    for complexity in sorted(set(r["complexity"] for r in results)):
        c_results = [r for r in results if r["complexity"] == complexity]
        c_success = sum(1 for r in c_results if r["success"])
        print(f"  Complexity {complexity}: {c_success}/{len(c_results)}")

    print("\nAudit events recorded:")
    print(f"  - CONTRACT_GENERATED: {len(arch_result.contracts)}")
    print(f"  - CONTRACT_DECOMPOSED: 1")
    print(f"  - CYCLE_COMPLETED: {len(results)}")
    print(f"\nSession ID: {session_id}")
    print("\nQuery audit with:")
    print(f'  python -c "import sqlite3, json; c=sqlite3.connect(\'.local/audit.db\'); print([json.loads(r[0]) for r in c.execute(\\"SELECT payload FROM audit_events WHERE session_id=\'{session_id}\' ORDER BY timestamp\\")])"')


if __name__ == "__main__":
    # Example requirement
    requirement = """
    Build a simple inventory management system with:
    - add_item(name, quantity, price) - adds item to inventory
    - get_item(name) - returns item details or None
    - update_quantity(name, delta) - adjusts quantity by delta (can be negative)
    - get_total_value() - returns sum of (quantity * price) for all items
    - get_low_stock(threshold) - returns list of items with quantity < threshold
    """

    # Allow custom requirement from command line
    if len(sys.argv) > 1:
        requirement = " ".join(sys.argv[1:])

    run_full_flow(requirement)
