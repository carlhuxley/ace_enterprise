#!/usr/bin/env python3
"""Test the full architect → broker → builder flow with escalation.

This script demonstrates:
1. Architect (Llama 3.3 70B) generates contracts from requirements
2. Broker routes each contract starting with cheapest viable agent
3. On failure, escalates to more capable (expensive) agent
4. Audit captures everything including escalations

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
from src.broker.contract_architect import create_architect_from_config
from src.broker.contract_driven import ContractValidator
from src.broker.performance_aggregator import PerformanceAggregator
from src.utils.llm_client import LLMClient


# =============================================================================
# AGENT POOL - ORDERED BY COST (CHEAPEST FIRST)
# =============================================================================

AGENT_TIERS = [
    {
        "id": "togetherai-Qwen2.5-7B-Instruct-Turbo",
        "provider": "togetherai",
        "model": "Qwen/Qwen2.5-7B-Instruct-Turbo",
        "base_url": "https://api.together.xyz/v1",
        "tier": 1,
        "cost": "low",
        "max_complexity": 3,  # Good for simple-medium tasks
    },
    {
        "id": "togetherai-Llama-3.3-70B-Instruct-Turbo",
        "provider": "togetherai",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "base_url": "https://api.together.xyz/v1",
        "tier": 2,
        "cost": "high",
        "max_complexity": 6,  # Can handle complex tasks
    },
]

# Architect configuration
ARCHITECT_PROVIDER = "togetherai"
ARCHITECT_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
ARCHITECT_BASE_URL = "https://api.together.xyz/v1"

AUDIT_DB_URL = "sqlite:///.local/audit.db"

# Escalation thresholds
MIN_SUCCESS_RATE = 0.20  # Don't use agent if <20% success at this complexity
MIN_SAMPLES = 3  # Need at least 3 samples before trusting success rate


def create_llm_client(agent_config: dict) -> LLMClient:
    """Create LLM client from agent config."""
    return LLMClient(
        provider=agent_config["provider"],
        model=agent_config["model"],
        base_url=agent_config["base_url"],
    )


def get_agent_success_rate(aggregator: PerformanceAggregator, agent_id: str, complexity: int) -> tuple[float, int]:
    """Get agent's success rate at a specific complexity level.

    Returns: (success_rate, sample_count)
    """
    try:
        metrics = aggregator.get_agent_metrics(agent_id)
        if complexity in metrics.success_by_complexity:
            rate = metrics.success_by_complexity[complexity]
            # Estimate samples from total tasks
            samples = max(1, metrics.total_tasks // len(metrics.success_by_complexity)) if metrics.success_by_complexity else 0
            return rate, samples
        return 0.5, 0  # No data, assume 50%
    except Exception:
        return 0.5, 0  # No data


def select_starting_agent(aggregator: PerformanceAggregator, complexity: int) -> dict:
    """Select cheapest agent that can handle this complexity with acceptable success rate."""

    for agent in AGENT_TIERS:
        # Skip if complexity exceeds agent's max
        if complexity > agent["max_complexity"]:
            continue

        # Check historical success rate
        success_rate, samples = get_agent_success_rate(aggregator, agent["id"], complexity)

        # If we have enough samples and success rate is too low, skip
        if samples >= MIN_SAMPLES and success_rate < MIN_SUCCESS_RATE:
            print(f"    Skipping {agent['id']}: {success_rate:.0%} @ complexity {complexity} ({samples} samples)")
            continue

        return agent

    # Fallback to most capable
    return AGENT_TIERS[-1]


def get_next_tier_agent(current_agent: dict) -> dict | None:
    """Get the next tier agent for escalation."""
    current_tier = current_agent["tier"]
    for agent in AGENT_TIERS:
        if agent["tier"] > current_tier:
            return agent
    return None  # Already at highest tier


def run_full_flow(requirement: str):
    """Run the full architect → broker → builder flow with escalation."""
    print("=" * 70)
    print("CONTRACT-DRIVEN TDD: ARCHITECT → BROKER → BUILDER (WITH ESCALATION)")
    print("=" * 70)
    print(f"\nRequirement: {requirement}\n")

    # Initialize audit
    audit = LocalAuditClient(AUDIT_DB_URL)
    session_id = f"architect-flow-{int(time.time())}"

    # Initialize performance aggregator
    print("-" * 70)
    print("INITIALIZING BROKER")
    print("-" * 70)

    audit_store = AuditStore(AUDIT_DB_URL)
    aggregator = PerformanceAggregator(audit_store)

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

    # Phase 2: Builder implements with escalation
    print("-" * 70)
    print("PHASE 2: BUILD WITH ESCALATION (cheap → expensive)")
    print("-" * 70)

    validator = ContractValidator()
    results = []

    for contract in arch_result.contracts:
        print(f"\n[{contract.id}] {contract.function_name} (complexity {contract.complexity})")

        interface = contract.to_interface_contract()
        prompt = interface.to_prompt()

        # Select starting agent (cheapest viable)
        current_agent = select_starting_agent(aggregator, contract.complexity)
        print(f"  Starting with: {current_agent['id']} (tier {current_agent['tier']}, {current_agent['cost']} cost)")

        success = False
        total_attempts = 0
        escalations = 0
        agents_tried = []
        max_attempts_per_agent = 2  # Try each agent twice before escalating

        while not success and current_agent is not None:
            agents_tried.append(current_agent["id"])
            builder_llm = create_llm_client(current_agent)
            agent_start_time = time.time()

            for attempt in range(max_attempts_per_agent):
                total_attempts += 1
                print(f"  [{current_agent['id'].split('-')[-1]}] Attempt {attempt + 1}...", end=" ", flush=True)

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
                    print("FAILED")

            agent_elapsed = time.time() - agent_start_time

            # Audit this agent's attempt
            audit.emit_simple(
                event_type=AuditEventType.CYCLE_COMPLETED,
                actor_id=current_agent["id"],
                payload={
                    "contract_id": contract.id,
                    "function_name": contract.function_name,
                    "complexity": contract.complexity,
                    "attempts": min(attempt + 1, max_attempts_per_agent),
                    "elapsed_seconds": agent_elapsed,
                    "success": success,
                    "tier": current_agent["tier"],
                    "escalation_number": escalations,
                },
                session_id=session_id,
            )

            if not success:
                # Try to escalate
                next_agent = get_next_tier_agent(current_agent)
                if next_agent:
                    escalations += 1
                    print(f"  ↑ ESCALATING to tier {next_agent['tier']} ({next_agent['id'].split('/')[-1]})")
                    current_agent = next_agent
                else:
                    print(f"  ✗ No higher tier available")
                    current_agent = None

        results.append({
            "contract_id": contract.id,
            "function_name": contract.function_name,
            "complexity": contract.complexity,
            "success": success,
            "total_attempts": total_attempts,
            "escalations": escalations,
            "agents_tried": agents_tried,
            "final_agent": agents_tried[-1] if agents_tried else None,
        })

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    success_count = sum(1 for r in results if r["success"])
    total_escalations = sum(r["escalations"] for r in results)
    total_attempts = sum(r["total_attempts"] for r in results)

    print(f"\nContracts: {len(results)}")
    print(f"Successful: {success_count}/{len(results)}")
    print(f"Total attempts: {total_attempts}")
    print(f"Total escalations: {total_escalations}")

    print("\nBy complexity:")
    for complexity in sorted(set(r["complexity"] for r in results)):
        c_results = [r for r in results if r["complexity"] == complexity]
        c_success = sum(1 for r in c_results if r["success"])
        c_escalations = sum(r["escalations"] for r in c_results)
        print(f"  Complexity {complexity}: {c_success}/{len(c_results)} ({c_escalations} escalations)")

    print("\nDetails:")
    for r in results:
        status = "✓" if r["success"] else "✗"
        agents = " → ".join([a.split("-")[-1] for a in r["agents_tried"]])
        esc = f" ({r['escalations']} esc)" if r["escalations"] > 0 else ""
        print(f"  {status} [{r['contract_id']}] {r['function_name']}: {agents}{esc}")

    print(f"\nSession ID: {session_id}")


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
