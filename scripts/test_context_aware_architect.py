#!/usr/bin/env python3
"""Test context-aware module architect with job_tracker.

This demonstrates:
1. Extracting context from existing codebase
2. Generating a contract that understands existing functions/schema
3. Capturing module dependencies in the audit

Run: python scripts/test_context_aware_architect.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.audit.local_client import LocalAuditClient
from src.contracts.module_architect import (
    ModuleArchitect,
    CodebaseContext,
    ExistingFunction,
    SchemaTable,
    extract_context_from_file,
)
from src.utils.llm_client import LLMClient


AUDIT_DB_URL = "sqlite:///.local/audit.db"
JOB_TRACKER_PATH = "/home/ch_dev/job_tracker"


def build_job_tracker_context() -> CodebaseContext:
    """Build context from the job_tracker codebase."""
    print("Extracting context from job_tracker...")

    # Try auto-extraction first
    impl_path = f"{JOB_TRACKER_PATH}/src/implementation.py"
    try:
        ctx = extract_context_from_file(impl_path)
        print(f"  Auto-extracted {len(ctx.existing_functions)} functions")
        print(f"  Found tables: {[t.name for t in ctx.schema]}")
        print(f"  Patterns: {ctx.patterns}")
    except Exception as e:
        print(f"  Auto-extraction failed: {e}")
        ctx = CodebaseContext()

    # Enrich with manual schema (auto-extraction doesn't get columns)
    ctx.schema = [
        SchemaTable(
            name="applications",
            columns=["id", "name", "description", "status", "company", "position", "date_applied", "updated_at"],
            primary_key="id",
        )
    ]

    # Add any missing patterns
    if "Use get_db() for database connections" not in ctx.patterns:
        ctx.patterns.append("Use get_db() for database connections")
    ctx.patterns.append("Return dict for single records (matching get_application format)")
    ctx.patterns.append("Return list[dict] for multiple records")

    return ctx


def test_context_aware_architect():
    """Test generating a new feature with context awareness."""
    print("=" * 70)
    print("CONTEXT-AWARE MODULE ARCHITECT")
    print("=" * 70)

    # Build context
    context = build_job_tracker_context()

    print(f"\nContext summary:")
    print(f"  Functions: {len(context.existing_functions)}")
    for f in context.existing_functions[:5]:
        print(f"    - {f.name}{f.signature}")
    if len(context.existing_functions) > 5:
        print(f"    ... and {len(context.existing_functions) - 5} more")

    print(f"\n  Schema:")
    for t in context.schema:
        print(f"    - {t.name}: {', '.join(t.columns[:5])}...")

    print(f"\n  Patterns:")
    for p in context.patterns[:3]:
        print(f"    - {p}")

    # New feature requirement
    requirement = """
    Add a search feature that:
    - search_applications(query: str) -> list[dict]
    - Searches across name, description, company, and position fields
    - Returns list of matching applications in the same format as get_application
    - Case-insensitive partial matching
    """

    print(f"\nRequirement: {requirement.strip()}")

    # Generate contract with context
    print("\n" + "-" * 70)
    print("GENERATING CONTRACT (with context)")
    print("-" * 70)

    audit = LocalAuditClient(AUDIT_DB_URL)
    session_id = f"context-architect-{int(time.time())}"

    # Use OpenRouter free model
    llm = LLMClient(provider="openrouter", model="openrouter/free")

    architect = ModuleArchitect(
        llm_client=llm,
        audit_client=audit,
        model_id="openrouter-auto",
    )

    result = architect.generate_module_contract(
        requirement=requirement,
        session_id=session_id,
        context=context,  # Pass the context!
    )

    if not result.success:
        print(f"\nERROR: {result.error}")
        return

    contract = result.contract
    print(f"\nGenerated contract in {result.elapsed_seconds:.2f}s")
    print(f"\nModule: {contract.name}")
    print(f"Description: {contract.description}")
    print(f"Complexity: {contract.complexity}")

    print(f"\nDependencies:")
    print(f"  Depends on: {contract.dependencies.depends_on}")
    print(f"  Provides: {contract.dependencies.provides}")
    print(f"  Tables read: {contract.dependencies.tables_read}")
    print(f"  Tables write: {contract.dependencies.tables_write}")

    print(f"\nFunctions:")
    for f in contract.functions:
        print(f"  - {f.name}{f.signature}")
        print(f"      {f.docstring}")

    print(f"\nIntegration tests:")
    for t in contract.integration_tests:
        print(f"  - {t.name}")
        print(f"      Setup: {t.setup}")
        print(f"      Steps: {t.steps}")
        print(f"      Assert: {t.assertion}")

    print(f"\nHints:")
    for h in contract.hints:
        print(f"  - {h}")

    print(f"\nSession ID: {session_id}")

    # Check audit captured dependencies
    print("\n" + "-" * 70)
    print("AUDIT CHECK")
    print("-" * 70)

    import sqlite3
    conn = sqlite3.connect('.local/audit.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT payload FROM audit_events
        WHERE session_id = ? AND event_type = 'CONTRACT_GENERATED'
        ORDER BY id DESC LIMIT 1
    ''', (session_id,))
    row = cursor.fetchone()
    if row:
        import json
        payload = json.loads(row[0])
        print(f"\nAudit captured:")
        print(f"  depends_on: {payload.get('depends_on')}")
        print(f"  provides: {payload.get('provides')}")
        print(f"  tables_read: {payload.get('tables_read')}")
        print(f"  has_context: {payload.get('has_context')}")
    conn.close()


if __name__ == "__main__":
    test_context_aware_architect()
