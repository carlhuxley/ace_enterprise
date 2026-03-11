#!/usr/bin/env python3
"""
Demo: Prompt-Level Distillation with Real Playbook Data

Shows how the PLD system:
1. Clusters bullets from playbooks
2. Routes queries to domain-specific distillation sets
3. Filters bullets by provenance (teacher → student compatibility)
4. Generates optimized system prompts for weak models
"""

import json
from pathlib import Path

from src.playbook.clustering import BulletClusterer, build_distillation_playbook
from src.playbook.distillation_router import (
    DistillationRouter,
    RouterConfig,
    Provenance,
    Supplier,
    LicenseCategory,
    classify_license,
    detect_supplier,
    filter_bullets_by_provenance,
)
from src.playbook.manager import PlaybookManager
from src.storage.schemas import Bullet, Playbook, PlaybookMetadata


def load_playbooks_from_archive() -> PlaybookManager:
    """Load playbooks from the archive directory."""
    manager = PlaybookManager(storage_path="data/playbooks_demo")

    archive_path = Path("data/playbooks_archive_general_models")
    for json_file in archive_path.glob("*.json"):
        with open(json_file) as f:
            data = json.load(f)

        # Skip empty playbooks
        if data["metadata"]["total_bullets"] == 0:
            continue

        # Reconstruct playbook
        sections = {}
        for section_name, bullets_data in data["sections"].items():
            bullets = []
            for b in bullets_data:
                bullet = Bullet(
                    id=b["id"],
                    content=b["content"],
                    section=b["section"],
                    tags=b.get("tags", []),
                    helpful_count=b.get("helpful_count", 0),
                    harmful_count=b.get("harmful_count", 0),
                    created_at=b.get("created_at"),
                    embedding=b.get("embedding"),
                    # Add provenance from base_model
                    created_by_model=data["metadata"].get("base_model"),
                )
                bullets.append(bullet)
            sections[section_name] = bullets

        playbook = Playbook(
            playbook_id=data["playbook_id"],
            version=data["version"],
            metadata=PlaybookMetadata(**data["metadata"]),
            sections=sections,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

        manager._playbooks[playbook.playbook_id] = playbook

    return manager


def demo_clustering(manager: PlaybookManager):
    """Demo: DBSCAN clustering on playbook bullets."""
    print("\n" + "=" * 60)
    print("DEMO 1: DBSCAN Clustering")
    print("=" * 60)

    # Collect all bullets
    all_bullets = []
    for playbook in manager._playbooks.values():
        for section_bullets in playbook.sections.values():
            all_bullets.extend(section_bullets)

    print(f"\nTotal bullets loaded: {len(all_bullets)}")

    # Cluster them
    clusterer = BulletClusterer(eps=0.3, min_samples=2)
    result = clusterer.cluster(all_bullets)

    print(f"Clusters found: {result.n_clusters}")
    print(f"Outliers: {result.n_outliers}")
    print(f"Distillation set size: {len(result.distillation_set)}")

    print("\nCluster details:")
    for cluster in result.clusters:
        rep = cluster.representative
        print(f"\n  Cluster {cluster.cluster_id} ({cluster.size} bullets):")
        print(f"    Representative: {rep.content[:80]}...")
        print(f"    Helpful count: {rep.helpful_count}")


def demo_provenance():
    """Demo: Provenance detection and matching."""
    print("\n" + "=" * 60)
    print("DEMO 2: Provenance Detection")
    print("=" * 60)

    test_models = [
        ("gpt-4o", "openai"),
        ("claude-3-opus", "anthropic"),
        ("gemini-pro", "google"),
        ("gemma-7b", "ollama"),
        ("qwen2.5-72b", "ollama"),
        ("llama-3.1-70b", "ollama"),
        ("mistral-7b", "ollama"),
    ]

    print("\nModel → Supplier / License:")
    print("-" * 50)
    for model, provider in test_models:
        supplier = detect_supplier(model, provider)
        license_cat = classify_license(model, provider)
        print(f"  {model:20} → {supplier.value:12} / {license_cat.value}")


def demo_provenance_filtering(manager: PlaybookManager):
    """Demo: Filtering bullets by provenance."""
    print("\n" + "=" * 60)
    print("DEMO 3: Provenance Filtering")
    print("=" * 60)

    # Collect bullets (they're from Qwen)
    all_bullets = []
    for playbook in manager._playbooks.values():
        for section_bullets in playbook.sections.values():
            all_bullets.extend(section_bullets)

    print(f"\nSource bullets: {len(all_bullets)} (from Qwen - Alibaba open source)")

    # Test different student models
    students = [
        ("qwen2.5-7b", "ollama", "Same supplier (Alibaba)"),
        ("llama-3.1-8b", "ollama", "Cross-supplier open source (Meta)"),
        ("gpt-4o-mini", "openai", "Cross-supplier proprietary (OpenAI)"),
        ("claude-3-haiku", "anthropic", "Cross-supplier proprietary (Anthropic)"),
    ]

    print("\nFiltering for different students:")
    print("-" * 60)

    for model, provider, desc in students:
        student_prov = Provenance.from_model(model, provider)

        # Filter with strict mode (no cross-supplier proprietary)
        filtered = filter_bullets_by_provenance(
            all_bullets,
            student_prov,
            allow_cross_supplier_proprietary=False
        )

        print(f"\n  Student: {model} ({desc})")
        print(f"    Supplier: {student_prov.supplier.value}")
        print(f"    License: {student_prov.license_category.value}")
        print(f"    Bullets available: {len(filtered)}/{len(all_bullets)}")


def demo_routing(manager: PlaybookManager):
    """Demo: Full routing with domain classification."""
    print("\n" + "=" * 60)
    print("DEMO 4: Domain Routing")
    print("=" * 60)

    # Create router
    config = RouterConfig(
        high_confidence_threshold=0.5,  # Lower for demo
        low_confidence_threshold=0.3,
        allow_cross_supplier_proprietary=False,
    )

    router = DistillationRouter(manager, config=config)

    print(f"\nAvailable domains: {router.get_all_domains()}")

    # Test queries with different student models
    test_cases = [
        ("Implement OAuth2 refresh token handling", "qwen2.5-7b", "ollama"),
        ("How to validate JWT tokens securely", "llama-3.1-8b", "ollama"),
        ("Implement OAuth2 refresh token handling", "gpt-4o-mini", "openai"),
    ]

    for query, student_model, student_provider in test_cases:
        print(f"\n{'─' * 60}")
        print(f"Query: {query[:50]}...")
        print(f"Student: {student_model} ({student_provider})")

        result = router.route_to_domain(
            domain="oauth_authentication",
            query=query,
            student_model=student_model,
            student_provider=student_provider,
        )

        print(f"\n  Verdict: {result.verdict.value}")
        print(f"  Bullets in prompt: {len(result.distillation_bullets)}")
        print(f"  Filtered by provenance: {result.bullets_filtered_by_provenance}")

        if result.student_provenance:
            print(f"  Student provenance: {result.student_provenance.supplier.value} / {result.student_provenance.license_category.value}")

        if result.use_teacher:
            print(f"  Recommended teacher: {result.recommended_teacher_supplier}")
        elif result.system_prompt:
            # Show first part of system prompt
            lines = result.system_prompt.split('\n')[:10]
            print(f"\n  System prompt preview:")
            for line in lines:
                print(f"    {line}")
            print("    ...")


def demo_system_prompt_generation(manager: PlaybookManager):
    """Demo: Full system prompt generation."""
    print("\n" + "=" * 60)
    print("DEMO 5: Generated System Prompt")
    print("=" * 60)

    config = RouterConfig(
        allow_cross_supplier_proprietary=False,
        max_bullets_in_prompt=10,
    )

    router = DistillationRouter(manager, config=config)

    # Route for an open source student
    result = router.route_to_domain(
        domain="oauth_authentication",
        query="Implement secure OAuth2 token refresh",
        student_model="qwen2.5-7b",
        student_provider="ollama",
    )

    if result.system_prompt:
        print("\nGenerated PLD System Prompt:")
        print("─" * 60)
        print(result.system_prompt)
        print("─" * 60)
        print(f"\nPrompt length: {len(result.system_prompt)} chars")
        print(f"Bullets included: {len(result.distillation_bullets)}")


if __name__ == "__main__":
    print("Loading playbooks from archive...")
    manager = load_playbooks_from_archive()
    print(f"Loaded {len(manager._playbooks)} playbooks")

    demo_clustering(manager)
    demo_provenance()
    demo_provenance_filtering(manager)
    demo_routing(manager)
    demo_system_prompt_generation(manager)

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)
