#!/usr/bin/env python3
"""Test the full architect → broker → builder flow with audit tracking.

This script demonstrates:
1. Architect (Llama 3.3 70B) generates contracts from requirements
2. Broker routes each contract to the best builder based on complexity
3. Builder implements each contract
4. Audit captures everything, broker learns for next time

Run: python scripts/test_architect_flow.py
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.audit.local_client import LocalAuditClient
from src.audit.schemas import AuditEventType
from src.audit.store import AuditStore
from src.broker.adaptive_broker import AdaptiveBroker, BrokerConfig
from src.broker.contract_architect import create_architect_from_config
from src.broker.contract_driven import ContractValidator
from src.broker.performance_aggregator import PerformanceAggregator
from src.utils.llm_client import LLMClient


# =============================================================================
# AGENT POOL CONFIGURATION
# =============================================================================
# Define available agents with their capabilities and costs

AGENT_POOL = {
    "togetherai-Qwen2.5-1.5B-Instruct-Turbo": {
        "provider": "togetherai",
        "model": "Qwen/Qwen2.5-1.5B-Instruct-Turbo",
        "base_url": "https://api.together.xyz/v1",
        "cost_tier": "low",
        "max_complexity": 2,  # Good for simple tasks
    },
    "togetherai-Qwen2.5-7B-Instruct-Turbo": {
        "provider": "togetherai",
        "model": "Qwen/Qwen2.5-7B-Instruct-Turbo",
        "base_url": "https://api.together.xyz/v1",
        "cost_tier": "medium",
        "max_complexity": 4,  # Good for moderate tasks
    },
    "togetherai-Llama-3.3-70B-Instruct-Turbo": {
        "provider": "togetherai",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "base_url": "https://api.together.xyz/v1",
        "cost_tier": "high",
        "max_complexity": 6,  # Can handle complex tasks
    },
}

# Architect configuration (always use capable model for decomposition)
ARCHITECT_PROVIDER = "togetherai"
ARCHITECT_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
ARCHITECT_BASE_URL = "https://api.together.xyz/v1"

# Fallback agent when broker has no data
FALLBACK_AGENT = "togetherai-Qwen2.5-7B-Instruct-Turbo"

AUDIT_DB_URL = "sqlite:///.local/audit.db"


def create_llm_client(agent_id: str) -> LLMClient:
    """Create LLM client for an agent from the pool."""
    if agent_id not in AGENT_POOL:
        raise ValueError(f"Unknown agent: {agent_id}")

    config = AGENT_POOL[agent_id]
    return LLMClient(
        provider=config["provider"],
        model=config["model"],
        base_url=config["base_url"],
    )


def run_full_flow(requirement: str):
    """Run the full architect → broker → builder flow."""
    print("=" * 70)
    print("CONTRACT-DRIVEN TDD: ARCHITECT → BROKER → BUILDER FLOW")
    print("=" * 70)
    print(f"\nRequirement: {requirement}\n")

    # Initialize audit
    audit = LocalAuditClient(AUDIT_DB_URL)
    session_id = f"architect-flow-{int(time.time())}"

    # Initialize broker with performance aggregator
    print("-" * 70)
    print("INITIALIZING BROKER")
    print("-" * 70)

    audit_store = AuditStore(AUDIT_DB_URL)
    aggregator = PerformanceAggregator(audit_store)
    broker = AdaptiveBroker(
        aggregator=aggregator,
        config=BrokerConfig(
            apply_threshold=0.70,
            ask_threshold=0.35,
            complexity_weight=0.4,  # Weight complexity heavily
            task_type_weight=0.2,
            overall_weight=0.4,
            fallback_agent=FALLBACK_AGENT,
        ),
    )

    # Show what broker knows
    all_metrics = aggregator.get_all_agent_metrics()
    if all_metrics:
        print(f"Broker has data on {len(all_metrics)} agents:")
        for agent_id, metrics in all_metrics.items():
            print(f"  {agent_id}: {metrics.success_rate:.0%} success ({metrics.total_tasks} tasks)")
            if metrics.success_by_complexity:
                for c, rate in sorted(metrics.success_by_complexity.items()):
                    print(f"    complexity {c}: {rate:.0%}")
    else:
        print("Broker has no historical data yet (cold start)")
    print()

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

    # Phase 2: Broker routes, Builder implements
    print("-" * 70)
    print("PHASE 2: BROKER ROUTES → BUILDER IMPLEMENTS")
    print("-" * 70)

    validator = ContractValidator()
    results = []
    routing_decisions = []

    for contract in arch_result.contracts:
        print(f"\n[{contract.id}] {contract.function_name} (complexity {contract.complexity})")

        # ASK BROKER: Which agent should handle this?
        routing = broker.route_task(complexity=contract.complexity)

        selected_agent = routing.selected_agent

        # Ensure selected agent is in our pool
        if selected_agent not in AGENT_POOL:
            print(f"  Broker suggested unknown agent '{selected_agent}', using fallback")
            selected_agent = FALLBACK_AGENT

        print(f"  Broker decision: {routing.verdict} → {selected_agent}")
        print(f"    Confidence: {routing.confidence:.2f}")
        if routing.candidates:
            print(f"    Candidates: {[(a, f'{s:.2f}') for a, s in routing.candidates[:3]]}")

        routing_decisions.append({
            "contract_id": contract.id,
            "complexity": contract.complexity,
            "selected_agent": selected_agent,
            "verdict": routing.verdict,
            "confidence": routing.confidence,
        })

        # Get LLM client for selected agent
        builder_llm = create_llm_client(selected_agent)

        interface = contract.to_interface_contract()
        prompt = interface.to_prompt()

        start_time = time.time()
        success = False
        attempts = 0
        max_attempts = 3

        for attempt in range(max_attempts):
            attempts = attempt + 1
            print(f"  Attempt {attempts}...", end=" ", flush=True)

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

        # Audit: CYCLE_COMPLETED (broker will learn from this)
        audit.emit_simple(
            event_type=AuditEventType.CYCLE_COMPLETED,
            actor_id=selected_agent,
            payload={
                "contract_id": contract.id,
                "function_name": contract.function_name,
                "complexity": contract.complexity,
                "attempts": attempts,
                "elapsed_seconds": elapsed,
                "success": success,
                "architect_model": arch_result.architect_model,
                "routing_verdict": routing.verdict,
                "routing_confidence": routing.confidence,
            },
            session_id=session_id,
        )

        results.append({
            "contract_id": contract.id,
            "function_name": contract.function_name,
            "complexity": contract.complexity,
            "selected_agent": selected_agent,
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

    print("\nRouting decisions:")
    for decision in routing_decisions:
        status = "✓" if any(r["contract_id"] == decision["contract_id"] and r["success"] for r in results) else "✗"
        print(f"  {status} [{decision['contract_id']}] complexity {decision['complexity']} → {decision['selected_agent']} ({decision['verdict']})")

    print("\nBy agent:")
    agents_used = set(r["selected_agent"] for r in results)
    for agent in agents_used:
        agent_results = [r for r in results if r["selected_agent"] == agent]
        agent_success = sum(1 for r in agent_results if r["success"])
        print(f"  {agent}: {agent_success}/{len(agent_results)}")

    print("\nAudit events recorded:")
    print(f"  - CONTRACT_GENERATED: {len(arch_result.contracts)}")
    print(f"  - CONTRACT_DECOMPOSED: 1")
    print(f"  - CYCLE_COMPLETED: {len(results)}")
    print(f"\nSession ID: {session_id}")

    # Invalidate broker cache so next run sees new data
    broker.invalidate_cache()
    print("\nBroker cache invalidated - next run will use updated metrics.")


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
