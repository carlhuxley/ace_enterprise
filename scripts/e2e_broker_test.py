#!/usr/bin/env python3
"""End-to-end test of the Capability Broker system with effGen agents.

This script:
1. Registers multiple effGen agents with different capabilities
2. Creates tasks and gets broker recommendations based on requirements
3. Routes tasks to appropriate agents
4. Records results in audit trail
5. Shows dashboard analysis

Run from ace_enterprise root:
    python scripts/e2e_broker_test.py
"""

import subprocess
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.broker.capability_registry import CapabilityRegistry
from src.broker.advisor import BrokerAdvisor, TaskRequirements
from src.broker.effgen_adapter import EffGenAdapter, EffGenAgentConfig
from src.broker.human_decision import HumanDecisionInterface, HumanDecision
from src.audit.local_client import LocalAuditClient
from src.audit.dashboard import AuditDashboard, AgentIdentity
from src.audit.schemas import AuditEventType


def run_calculator_task(prompt: str) -> dict:
    """Execute a math task using the calculator agent."""
    test_script = f'''
import sys
sys.path.insert(0, "{Path.home() / 'effgen_test'}")
import logging
logging.basicConfig(level=logging.WARNING)

from effgen import Agent, load_model
from effgen.core.agent import AgentConfig
from effgen.tools.builtin import Calculator, PythonREPL, CodeExecutor

model = load_model("Qwen/Qwen2.5-1.5B-Instruct", quantization="4bit")
config = AgentConfig(
    name="calculator_agent",
    model=model,
    tools=[CodeExecutor(), Calculator(), PythonREPL()],
    system_prompt="You are a helpful assistant that solves math problems. Use the calculator tool."
)
agent = Agent(config=config)
result = agent.run("{prompt}")
print(f"OUTPUT:{{result.output}}")
print(f"SUCCESS:{{result.success}}")
'''
    return _run_effgen_script(test_script)


def run_search_task(prompt: str) -> dict:
    """Execute a search/knowledge task using the search agent."""
    # For this test, we use a simpler approach - the search agent answers general questions
    test_script = f'''
import sys
sys.path.insert(0, "{Path.home() / 'effgen_test'}")
import logging
logging.basicConfig(level=logging.WARNING)

from effgen import Agent, load_model
from effgen.core.agent import AgentConfig
from effgen.tools.builtin import PythonREPL

model = load_model("Qwen/Qwen2.5-1.5B-Instruct", quantization="4bit")
config = AgentConfig(
    name="search_agent",
    model=model,
    tools=[PythonREPL()],
    system_prompt="You are a knowledgeable assistant. Answer questions directly and concisely."
)
agent = Agent(config=config)
result = agent.run("{prompt}")
print(f"OUTPUT:{{result.output}}")
print(f"SUCCESS:{{result.success}}")
'''
    return _run_effgen_script(test_script)


def _run_effgen_script(test_script: str) -> dict:
    """Run an effGen script and return results."""
    try:
        effgen_python = Path.home() / "effgen_test" / ".venv" / "bin" / "python"
        result = subprocess.run(
            [str(effgen_python), "-c", test_script],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path.home() / "effgen_test"),
        )

        output = result.stdout
        success = "SUCCESS:True" in output

        if "OUTPUT:" in output:
            actual_output = output.split("OUTPUT:")[1].split("\n")[0]
        else:
            actual_output = output

        return {
            "success": success,
            "output": actual_output,
            "stderr": result.stderr
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Timeout", "error": "Task exceeded 120s"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def execute_task(agent_ref: str, prompt: str) -> dict:
    """Route task execution to appropriate agent."""
    if "calculator" in agent_ref:
        return run_calculator_task(prompt)
    elif "search" in agent_ref:
        return run_search_task(prompt)
    else:
        return {"success": False, "output": "Unknown agent type"}


def main():
    print("=" * 70)
    print("END-TO-END CAPABILITY BROKER TEST (Multi-Agent)")
    print("=" * 70)

    # Initialize components
    print("\n[1] Initializing Capability Broker components...")
    registry = CapabilityRegistry()
    adapter = EffGenAdapter(registry)
    advisor = BrokerAdvisor(registry)
    audit_client = LocalAuditClient()

    print("    ✓ Registry, Adapter, Advisor, Audit initialized")

    # =========================================================================
    # REGISTER AGENTS
    # =========================================================================
    print("\n[2] Registering effGen agents...")

    # Agent 1: Calculator - good at math
    calculator_agent = EffGenAgentConfig(
        agent_ref="effgen-calculator-001",
        endpoint="http://localhost:8001",
        model_name="Qwen/Qwen2.5-1.5B-Instruct",
        capabilities={"math": 0.95, "calculation": 0.95, "python": 0.7}
    )
    adapter.register_agent(calculator_agent)
    print(f"    ✓ {calculator_agent.agent_ref}")
    print(f"      Capabilities: {calculator_agent.capabilities}")

    # Agent 2: Search - good at knowledge/search
    search_agent = EffGenAgentConfig(
        agent_ref="effgen-search-001",
        endpoint="http://localhost:8002",
        model_name="Qwen/Qwen2.5-1.5B-Instruct",
        capabilities={"search": 0.9, "knowledge": 0.85, "qa": 0.9, "python": 0.5}
    )
    adapter.register_agent(search_agent)
    print(f"    ✓ {search_agent.agent_ref}")
    print(f"      Capabilities: {search_agent.capabilities}")

    # Emit registration events
    for agent in [calculator_agent, search_agent]:
        audit_client.emit_simple(
            AuditEventType.AGENT_STARTED,
            actor_id="broker",
            payload={
                "agent_ref": agent.agent_ref,
                "model": agent.model_name,
                "capabilities": agent.capabilities
            }
        )

    # Audit data for human decision interface (identity + cost)
    audit_data = {
        calculator_agent.agent_ref: {
            "identity": "Qwen 2.5 1.5B Calculator",
            "cost_per_task": 0.001,
        },
        search_agent.agent_ref: {
            "identity": "Qwen 2.5 1.5B Search",
            "cost_per_task": 0.001,
        }
    }

    decision_interface = HumanDecisionInterface(advisor, audit_data)

    # =========================================================================
    # DEFINE TASKS
    # =========================================================================
    tasks = [
        {
            "id": "task-001",
            "requirements": {"math": 0.8},
            "prompt": "What is 23668 divided by 56, then multiplied by 45?",
            "type": "math"
        },
        {
            "id": "task-002",
            "requirements": {"qa": 0.7},
            "prompt": "What is the capital of France?",
            "type": "knowledge"
        },
        {
            "id": "task-003",
            "requirements": {"calculation": 0.8},
            "prompt": "Calculate the square root of 144 plus 25 squared",
            "type": "math"
        },
    ]

    # Track results for dashboard
    all_events = []
    task_results = []

    # =========================================================================
    # PROCESS TASKS
    # =========================================================================
    print("\n[3] Processing tasks...")

    for task_info in tasks:
        print(f"\n{'─' * 60}")
        print(f"TASK: {task_info['id']} ({task_info['type']})")
        print(f"Prompt: {task_info['prompt']}")
        print(f"Requirements: {task_info['requirements']}")

        # Create task requirements
        task = TaskRequirements(
            task_id=task_info["id"],
            capabilities=task_info["requirements"]
        )

        # Get broker recommendation
        recommendations = advisor.recommend(task)
        summary = advisor.get_summary(task)
        print(f"\nBroker: {summary}")

        if not recommendations:
            print("  ✗ No agents match!")
            continue

        for rec in recommendations:
            print(f"  → {rec.agent_ref}: match={rec.capability_match:.0%}")

        # Human sees full context
        context = decision_interface.get_context(task)
        print(f"\nHuman sees costs: ", end="")
        for agent_ref in [r.agent_ref for r in recommendations]:
            if agent_ref in context.audit_data:
                cost = context.audit_data[agent_ref].get("cost_per_task", "?")
                print(f"{agent_ref}=${cost}, ", end="")
        print()

        # Accept top recommendation
        chosen = recommendations[0].agent_ref
        decision = HumanDecision(
            task_id=task.task_id,
            chosen_agent_ref=chosen,
            decision_type="accept"
        )
        decision_interface.record_decision(decision)
        print(f"Decision: accept → {chosen}")

        # Execute
        print(f"\nExecuting on {chosen}...")
        result = execute_task(chosen, task_info["prompt"])

        print(f"Result: {result['output'][:100]}..." if len(result.get('output', '')) > 100 else f"Result: {result['output']}")
        print(f"Success: {result['success']}")

        # Record in audit
        audit_client.emit_simple(
            AuditEventType.CYCLE_COMPLETED,
            actor_id=chosen,
            payload={
                "task_id": task_info["id"],
                "task_type": task_info["type"],
                "success": result["success"],
                "prompt": task_info["prompt"],
                "output": result["output"][:200] if result.get("output") else "",
            }
        )

        # Track for dashboard
        all_events.append({
            "actor_id": chosen,
            "event_type": "CYCLE_COMPLETED",
            "payload": {"success": result["success"], "task_type": task_info["type"]}
        })
        task_results.append({
            "task": task_info["id"],
            "agent": chosen,
            "success": result["success"]
        })

    # =========================================================================
    # AUDIT & DASHBOARD
    # =========================================================================
    print(f"\n{'=' * 70}")
    print("AUDIT TRAIL & DASHBOARD")
    print("=" * 70)

    # Audit stats
    stats = audit_client.get_stats()
    print(f"\nAudit events: {stats['total_events']}")

    # Dashboard analysis
    dashboard = AuditDashboard(all_events)

    # Register identities (human visibility)
    dashboard.register_identity(calculator_agent.agent_ref, AgentIdentity(
        display_name="Qwen 2.5 1.5B Calculator",
        model_id="Qwen/Qwen2.5-1.5B-Instruct",
        provider="effGen (local)"
    ))
    dashboard.register_identity(search_agent.agent_ref, AgentIdentity(
        display_name="Qwen 2.5 1.5B Search",
        model_id="Qwen/Qwen2.5-1.5B-Instruct",
        provider="effGen (local)"
    ))

    # Inject costs
    calc_tasks = sum(1 for r in task_results if r["agent"] == calculator_agent.agent_ref)
    search_tasks = sum(1 for r in task_results if r["agent"] == search_agent.agent_ref)
    dashboard.inject_cost_data({
        calculator_agent.agent_ref: {"total_cost": calc_tasks * 0.001, "tasks": max(calc_tasks, 1)},
        search_agent.agent_ref: {"total_cost": search_tasks * 0.001, "tasks": max(search_tasks, 1)},
    })

    # Show report
    print("\n┌─────────────────────────────────────────────────────────────────┐")
    print("│                    DASHBOARD (Human View)                       │")
    print("├─────────────────────────────────────────────────────────────────┤")

    report = dashboard.get_full_report()
    for agent_ref, data in report.items():
        identity = data.get("identity", {}).get("display_name", agent_ref)
        perf = data.get("performance", {})
        costs = data.get("costs", {})

        success_rate = perf.get("success_rate", 0)
        total = perf.get("total_tasks", 0)
        cost_per = costs.get("cost_per_task", 0)

        print(f"│  {identity:<30} │")
        print(f"│    Tasks: {total}, Success: {success_rate:.0%}, Cost/task: ${cost_per:.4f}    │")
        print("├─────────────────────────────────────────────────────────────────┤")

    # Task type strengths
    strengths = dashboard.get_task_type_strengths()
    if strengths:
        print("│  TASK TYPE STRENGTHS:                                           │")
        for task_type, info in strengths.items():
            best = info.get("best_agent", "?")
            rate = info.get("success_rate", 0)
            print(f"│    {task_type}: {best} ({rate:.0%})                         │")

    print("└─────────────────────────────────────────────────────────────────┘")

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    total_success = sum(1 for r in task_results if r["success"])
    print(f"Tasks completed: {len(task_results)}")
    print(f"Success rate: {total_success}/{len(task_results)} ({100*total_success/len(task_results):.0f}%)")
    print(f"Routing: math→calculator, qa→search")


if __name__ == "__main__":
    main()
