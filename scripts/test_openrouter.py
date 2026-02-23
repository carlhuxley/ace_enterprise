#!/usr/bin/env python3
"""Test OpenRouter free models.

OpenRouter offers free tiers for several models:
- meta-llama/llama-3.1-8b-instruct:free
- google/gemma-2-9b-it:free
- qwen/qwen-2-7b-instruct:free
- mistralai/mistral-7b-instruct:free

Run: python scripts/test_openrouter.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.llm_client import LLMClient


# Free models available on OpenRouter (Feb 2026)
# Full list: curl -s https://openrouter.ai/api/v1/models | python -c "import json,sys; [print(m['id']) for m in json.load(sys.stdin)['data'] if m.get('pricing',{}).get('prompt')=='0']"
FREE_MODELS = [
    # Good for coding/TDD
    "qwen/qwen3-coder:free",                    # Qwen3 Coder - excellent for code
    "deepseek/deepseek-r1-0528:free",           # DeepSeek R1 - strong reasoning
    "meta-llama/llama-3.3-70b-instruct:free",   # Llama 3.3 70B - large capable model
    "mistralai/mistral-small-3.1-24b-instruct:free",  # Mistral Small
    # Smaller/faster options
    "google/gemma-3-27b-it:free",               # Gemma 3 27B
    "qwen/qwen3-4b:free",                       # Qwen3 4B - fast small model
    "meta-llama/llama-3.2-3b-instruct:free",    # Llama 3.2 3B - very fast
    # Auto-router
    "openrouter/free",                          # Auto-selects from free models
]


def test_model(model: str):
    """Test a single model with a simple prompt."""
    print(f"\nTesting {model}...")

    try:
        client = LLMClient(provider="openrouter", model=model)

        result = client.generate(
            prompt="Write a Python function that adds two numbers. Output ONLY the code.",
            temperature=0.3,
        )

        print(f"  Latency: {result['latency_ms']}ms")
        print(f"  Tokens: {result['tokens_used']}")
        print(f"  Response:\n{result['content'][:300]}...")
        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main():
    print("=" * 60)
    print("OPENROUTER FREE MODELS TEST")
    print("=" * 60)

    # Test just one model first
    if len(sys.argv) > 1:
        model = sys.argv[1]
        test_model(model)
    else:
        # Test all free models
        results = {}
        for model in FREE_MODELS:
            results[model] = test_model(model)

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        for model, success in results.items():
            status = "PASS" if success else "FAIL"
            print(f"  {model}: {status}")


if __name__ == "__main__":
    main()
