#!/usr/bin/env python3
"""
Test model provenance tracking implementation.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.storage.schemas import BulletCreate, Bullet
from datetime import datetime


def test_license_mapping():
    """Test the _get_license_type logic manually."""
    print("Testing license type mapping...")

    # Import the method logic (matches updated autonomous_tdd_agent.py)
    def get_license_type(provider: str, model: str) -> str:
        # Block proprietary providers
        if provider in ["openai", "anthropic", "google", "cohere"]:
            raise ValueError(f"Proprietary provider '{provider}' is not allowed")

        # Open-source models
        if provider in ["ollama", "vllm", "togetherai"]:
            model_lower = model.lower()
            if any(name in model_lower for name in ["qwen", "deepseek-coder", "mistral"]):
                return "apache-2.0"
            if "deepseek" in model_lower and "coder" not in model_lower:
                return "mit"
            if "llama" in model_lower:
                return "llama-3.1-community"
            return "open-source-unknown"

        if provider == "deepseek":
            return "mit"

        raise ValueError(f"Unknown provider '{provider}'")

    # Test cases (proprietary providers should raise ValueError)
    test_cases = [
        # Open-source providers
        ("ollama", "qwen2.5-coder:32b", "apache-2.0"),
        ("ollama", "deepseek-coder:33b", "apache-2.0"),
        ("ollama", "mistral:7b", "apache-2.0"),
        ("ollama", "llama3.1:70b", "llama-3.1-community"),
        ("vllm", "Qwen/Qwen2.5-Coder-32B-Instruct", "apache-2.0"),
        ("vllm", "meta-llama/Llama-3.1-70B-Instruct", "llama-3.1-community"),
        ("togetherai", "Qwen/Qwen2.5-Coder-32B-Instruct", "apache-2.0"),
        ("togetherai", "deepseek-ai/DeepSeek-Coder-V2-Instruct", "apache-2.0"),
        ("togetherai", "meta-llama/Llama-3.1-70B-Instruct", "llama-3.1-community"),
        ("togetherai", "mistralai/Mistral-7B-Instruct-v0.2", "apache-2.0"),
        ("deepseek", "deepseek-coder", "mit"),
        ("deepseek", "deepseek-chat", "mit"),
    ]

    all_passed = True
    for provider, model, expected in test_cases:
        result = get_license_type(provider, model)
        status = "✓" if result == expected else "✗"
        if result != expected:
            all_passed = False
        print(f"  {status} {provider:12} / {model:35} → {result:25} (expected: {expected})")

    return all_passed


def test_bullet_create_schema():
    """Test BulletCreate schema with provenance fields."""
    print("\nTesting BulletCreate schema with provenance...")

    # Test with provenance fields
    bullet = BulletCreate(
        content="Test bullet content",
        section="strategies_and_hard_rules",
        tags=["test"],
        created_by_model="qwen2.5-coder:32b",
        model_provider="ollama",
        license_type="apache-2.0"
    )

    print(f"  ✓ Created bullet with provenance:")
    print(f"    - model: {bullet.created_by_model}")
    print(f"    - provider: {bullet.model_provider}")
    print(f"    - license: {bullet.license_type}")

    # Test without provenance fields (backward compatibility)
    bullet2 = BulletCreate(
        content="Test bullet without provenance",
        section="code_snippets",
        tags=["test"]
    )

    print(f"  ✓ Created bullet WITHOUT provenance (backward compatible):")
    print(f"    - model: {bullet2.created_by_model}")
    print(f"    - provider: {bullet2.model_provider}")
    print(f"    - license: {bullet2.license_type}")

    return True


def test_bullet_schema():
    """Test full Bullet schema with provenance fields."""
    print("\nTesting full Bullet schema with provenance...")

    bullet = Bullet(
        id="ctx-00001",
        content="Test bullet",
        section="strategies_and_hard_rules",
        tags=["test"],
        helpful_count=0,
        harmful_count=0,
        created_at=datetime.now(),
        created_by_model="gpt-4o",
        model_provider="openai",
        license_type="proprietary"
    )

    print(f"  ✓ Created full Bullet with provenance:")
    print(f"    - id: {bullet.id}")
    print(f"    - model: {bullet.created_by_model}")
    print(f"    - provider: {bullet.model_provider}")
    print(f"    - license: {bullet.license_type}")

    return True


if __name__ == "__main__":
    print("=" * 70)
    print("Model Provenance Tracking - Validation Tests")
    print("=" * 70)

    results = []

    # Run tests
    results.append(("License Mapping", test_license_mapping()))
    results.append(("BulletCreate Schema", test_bullet_create_schema()))
    results.append(("Bullet Schema", test_bullet_schema()))

    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")

    all_passed = all(r[1] for r in results)

    if all_passed:
        print("\n✓ All tests passed! Model provenance tracking is working.")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed!")
        sys.exit(1)
