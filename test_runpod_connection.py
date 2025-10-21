#!/usr/bin/env python3
"""
Test RunPod vLLM connection before running full ensemble demo.
"""
import httpx
import sys

# RunPod configuration
# RunPod uses port mapping: internal -> external
# 8001 -> 33186, 8002 -> 33187, 8003 -> 33188
RUNPOD_IP = "103.196.86.55"
PORTS = [33186, 33187, 33188]  # External ports (mapped from 8001, 8002, 8003)
MODELS = [
    "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "Qwen/Qwen2.5-1.5B-Instruct",
    "Qwen/Qwen2.5-Coder-0.5B-Instruct",
]

def test_health_check(url: str) -> bool:
    """Test health endpoint."""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{url}/health")
            response.raise_for_status()
            print(f"✓ {url}/health - OK")
            return True
    except Exception as e:
        print(f"✗ {url}/health - FAILED: {e}")
        return False

def test_inference(url: str, model: str) -> bool:
    """Test inference endpoint."""
    try:
        payload = {
            "model": model,
            "prompt": "def hello():",
            "max_tokens": 50,
            "temperature": 0.7,
        }

        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{url}/v1/completions", json=payload)
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["text"]
            tokens = data["usage"]["total_tokens"]

            print(f"✓ {url}/v1/completions - OK")
            print(f"  Generated: {content[:50]}...")
            print(f"  Tokens used: {tokens}")
            return True

    except Exception as e:
        print(f"✗ {url}/v1/completions - FAILED: {e}")
        return False

def main():
    print("=" * 80)
    print("  RunPod vLLM Connection Test")
    print("=" * 80)
    print(f"\nRunPod IP: {RUNPOD_IP}")
    print(f"Testing ports: {', '.join(map(str, PORTS))}")

    all_passed = True

    for i, port in enumerate(PORTS):
        url = f"http://{RUNPOD_IP}:{port}"
        model = MODELS[i]

        print(f"\n{'-' * 80}")
        print(f"Testing Model {i+1}: {model}")
        print(f"Endpoint: {url}")
        print(f"{'-' * 80}")

        # Test health check
        health_ok = test_health_check(url)

        # Test inference (only if health check passed)
        inference_ok = False
        if health_ok:
            inference_ok = test_inference(url, model)

        if not (health_ok and inference_ok):
            all_passed = False

    print("\n" + "=" * 80)
    if all_passed:
        print("✓ All tests passed! RunPod vLLM is ready for ensemble learning.")
        print("\nYou can now run: python demo_ensemble_learning.py")
        sys.exit(0)
    else:
        print("✗ Some tests failed. Please check:")
        print("  1. RunPod pod is running")
        print("  2. Ports 8001, 8002, 8003 are exposed")
        print("  3. vLLM models are running (./start_vllm_multi.sh)")
        print("  4. IP address is correct")
        sys.exit(1)

if __name__ == "__main__":
    main()
