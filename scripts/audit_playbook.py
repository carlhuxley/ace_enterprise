#!/usr/bin/env python3
"""
Playbook Audit Tool - Model Provenance Analysis

Analyzes playbooks to show:
- Which playbooks contain proprietary bullets
- Which models created which bullets
- License distribution (proprietary vs. open-source)
- Potential licensing issues for commercialization
"""
import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.storage.schemas import Playbook


def load_playbook(playbook_path: Path) -> Playbook:
    """Load playbook from JSON file."""
    with open(playbook_path) as f:
        data = json.load(f)
    return Playbook(**data)


def audit_all_playbooks(playbook_dir: str = "data/playbooks") -> Dict:
    """Audit all playbooks in directory."""
    playbook_path = Path(playbook_dir)

    if not playbook_path.exists():
        print(f"Error: Playbook directory not found: {playbook_dir}")
        sys.exit(1)

    playbook_files = list(playbook_path.glob("*.json"))

    if not playbook_files:
        print(f"No playbook files found in {playbook_dir}")
        sys.exit(1)

    results = {
        "total_playbooks": len(playbook_files),
        "playbooks_with_proprietary": [],
        "playbooks_clean": [],
        "all_proprietary_bullets": [],
        "global_stats": {
            "total_bullets": 0,
            "proprietary_count": 0,
            "open_source_count": 0,
            "unknown_count": 0,
            "models": defaultdict(int),
            "licenses": defaultdict(int),
        }
    }

    for pb_file in sorted(playbook_files):
        try:
            playbook = load_playbook(pb_file)
            pb_stats = audit_single_playbook(playbook, pb_file.name)

            # Aggregate stats
            results["global_stats"]["total_bullets"] += pb_stats["total_bullets"]
            results["global_stats"]["proprietary_count"] += len(pb_stats["proprietary_bullets"])
            results["global_stats"]["open_source_count"] += len(pb_stats["open_source_bullets"])
            results["global_stats"]["unknown_count"] += len(pb_stats["unknown_bullets"])

            for model, count in pb_stats["models"].items():
                results["global_stats"]["models"][model] += count
            for license_type, count in pb_stats["licenses"].items():
                results["global_stats"]["licenses"][license_type] += count

            # Categorize playbooks
            if pb_stats["proprietary_bullets"]:
                results["playbooks_with_proprietary"].append({
                    "playbook_id": playbook.playbook_id,
                    "filename": pb_file.name,
                    "proprietary_count": len(pb_stats["proprietary_bullets"]),
                    "total_bullets": pb_stats["total_bullets"],
                    "bullets": pb_stats["proprietary_bullets"]
                })
                # Add to global list
                for bullet in pb_stats["proprietary_bullets"]:
                    bullet["playbook_id"] = playbook.playbook_id
                    bullet["playbook_file"] = pb_file.name
                results["all_proprietary_bullets"].extend(pb_stats["proprietary_bullets"])
            else:
                results["playbooks_clean"].append({
                    "playbook_id": playbook.playbook_id,
                    "filename": pb_file.name,
                    "total_bullets": pb_stats["total_bullets"]
                })

        except Exception as e:
            print(f"Warning: Failed to load {pb_file.name}: {e}")
            continue

    return results


def audit_single_playbook(playbook: Playbook, filename: str) -> Dict:
    """Audit a single playbook for model provenance."""
    stats = {
        "total_bullets": 0,
        "models": defaultdict(int),
        "licenses": defaultdict(int),
        "proprietary_bullets": [],
        "open_source_bullets": [],
        "unknown_bullets": [],
    }

    # Analyze all bullets across all sections
    for section_name, bullets in playbook.sections.items():
        for bullet in bullets:
            stats["total_bullets"] += 1

            # Check if provenance exists
            if bullet.created_by_model:
                stats["models"][bullet.created_by_model] += 1
                stats["licenses"][bullet.license_type or "unknown"] += 1

                # Categorize by license
                if bullet.license_type == "proprietary":
                    stats["proprietary_bullets"].append({
                        "bullet_id": bullet.id,
                        "model": bullet.created_by_model,
                        "provider": bullet.model_provider,
                        "section": section_name,
                        "content_preview": bullet.content[:100] + "..." if len(bullet.content) > 100 else bullet.content
                    })
                elif bullet.license_type and bullet.license_type != "unknown":
                    stats["open_source_bullets"].append({
                        "bullet_id": bullet.id,
                        "model": bullet.created_by_model,
                        "license": bullet.license_type,
                        "section": section_name
                    })
                else:
                    stats["unknown_bullets"].append({
                        "bullet_id": bullet.id,
                        "model": bullet.created_by_model or "unknown",
                        "section": section_name
                    })
            else:
                stats["unknown_bullets"].append({
                    "bullet_id": bullet.id,
                    "model": "unknown",
                    "section": section_name
                })

    return stats


def print_full_report(results: Dict):
    """Print comprehensive audit report."""
    print("=" * 80)
    print("PLAYBOOK AUDIT REPORT - Model Provenance Analysis")
    print("=" * 80)

    # Global overview
    print("\n📊 GLOBAL OVERVIEW")
    print(f"  Total playbooks scanned: {results['total_playbooks']}")
    print(f"  Total bullets: {results['global_stats']['total_bullets']}")
    print(f"  Proprietary bullets: {results['global_stats']['proprietary_count']} ({results['global_stats']['proprietary_count']/max(results['global_stats']['total_bullets'], 1)*100:.1f}%)")
    print(f"  Open-source bullets: {results['global_stats']['open_source_count']} ({results['global_stats']['open_source_count']/max(results['global_stats']['total_bullets'], 1)*100:.1f}%)")
    print(f"  Unknown provenance: {results['global_stats']['unknown_count']} ({results['global_stats']['unknown_count']/max(results['global_stats']['total_bullets'], 1)*100:.1f}%)")

    # License breakdown
    if results["global_stats"]["licenses"]:
        print("\n📜 GLOBAL LICENSE DISTRIBUTION")
        for license_type, count in sorted(results["global_stats"]["licenses"].items(), key=lambda x: x[1], reverse=True):
            pct = count / max(results["global_stats"]["total_bullets"], 1) * 100
            print(f"  {license_type:30} {count:4} bullets ({pct:5.1f}%)")

    # Model breakdown
    if results["global_stats"]["models"]:
        print("\n🤖 MODELS USED")
        for model, count in sorted(results["global_stats"]["models"].items(), key=lambda x: x[1], reverse=True):
            print(f"  {model:40} {count:4} bullets")

    # Playbooks with proprietary bullets (CRITICAL)
    if results["playbooks_with_proprietary"]:
        print("\n" + "=" * 80)
        print("⚠️  PLAYBOOKS WITH PROPRIETARY BULLETS (ToS Violation Risk)")
        print("=" * 80)
        print("\nThese playbooks contain bullets created by closed-source models.")
        print("Using these for training may violate provider ToS.\n")

        for pb in results["playbooks_with_proprietary"]:
            print(f"  📦 {pb['playbook_id']}")
            print(f"     File: {pb['filename']}")
            print(f"     Proprietary: {pb['proprietary_count']}/{pb['total_bullets']} bullets ({pb['proprietary_count']/pb['total_bullets']*100:.1f}%)")
            print()

        # List all proprietary bullets with playbook source
        print("\n" + "=" * 80)
        print(f"PROPRIETARY BULLETS DETAIL ({len(results['all_proprietary_bullets'])} total)")
        print("=" * 80)

        # Group by playbook
        by_playbook = defaultdict(list)
        for bullet in results["all_proprietary_bullets"]:
            by_playbook[bullet["playbook_id"]].append(bullet)

        for pb_id, bullets in sorted(by_playbook.items()):
            print(f"\n📦 {pb_id} ({bullets[0]['playbook_file']})")
            print(f"   {len(bullets)} proprietary bullets:\n")

            for bullet in bullets:
                print(f"   • {bullet['bullet_id']} ({bullet['model']} / {bullet['provider']})")
                print(f"     Section: {bullet['section']}")
                print(f"     Preview: {bullet['content_preview']}")
                print()

    # Clean playbooks
    if results["playbooks_clean"]:
        print("\n" + "=" * 80)
        print(f"✅ CLEAN PLAYBOOKS ({len(results['playbooks_clean'])} playbooks)")
        print("=" * 80)
        print("\nThese playbooks contain no proprietary bullets.\n")

        for pb in results["playbooks_clean"]:
            print(f"  ✓ {pb['playbook_id']}")
            print(f"    File: {pb['filename']}")
            print(f"    Bullets: {pb['total_bullets']}")
            print()

    # Recommendations
    print("\n" + "=" * 80)
    print("💡 RECOMMENDATIONS")
    print("=" * 80)

    if results["playbooks_with_proprietary"]:
        prop_count = len(results["playbooks_with_proprietary"])
        bullet_count = results["global_stats"]["proprietary_count"]

        print(f"\n⚠️  ACTION REQUIRED: {bullet_count} proprietary bullets found across {prop_count} playbook(s)")
        print("\n  To ensure legal compliance and enable commercialization:")
        print("\n  Option 1: Migrate to open-source models")
        print("    • Use Qwen/Qwen2.5-Coder-32B-Instruct (Apache 2.0)")
        print("    • Use deepseek-ai/DeepSeek-Coder-V2-Instruct (MIT)")
        print("    • Use meta-llama/Llama-3.1-70B-Instruct (Llama 3.1 Community)")
        print("    • Re-run demos to regenerate playbooks with open-source models")

        print("\n  Option 2: Delete affected playbooks")
        print("    • Remove playbooks containing proprietary bullets:")
        for pb in results["playbooks_with_proprietary"]:
            print(f"      rm data/playbooks/{pb['filename']}")

        print("\n  Option 3: Manual review")
        print("    • Review each proprietary bullet individually")
        print("    • Manually recreate with open-source models")
    else:
        print("\n✅ All playbooks are clean!")
        if results["global_stats"]["unknown_count"] > 0:
            print(f"  Note: {results['global_stats']['unknown_count']} bullets lack provenance tracking")
            print("  Consider re-generating with model provenance enabled")
        else:
            print("  All bullets have proper model attribution")
            print("  System is ready for commercialization!")

    print("\n" + "=" * 80)


def main():
    playbook_dir = "data/playbooks"

    if len(sys.argv) > 1:
        playbook_dir = sys.argv[1]

    print(f"Scanning playbooks in {playbook_dir}...\n")

    results = audit_all_playbooks(playbook_dir)
    print_full_report(results)


if __name__ == "__main__":
    main()
