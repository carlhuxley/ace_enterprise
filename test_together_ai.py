#!/usr/bin/env python3
"""Test Together AI API connection"""
import httpx
import json
import os

# Load API key
api_key = os.getenv("TOGETHERAI_API_KEY")
if not api_key:
    print("ERROR: TOGETHERAI_API_KEY not set")
    exit(1)

print(f"API Key loaded: {api_key[:20]}...")

# Test request
url = "https://api.together.xyz/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

payload = {
    "model": "Qwen/Qwen2.5-72B-Instruct-Turbo",
    "messages": [
        {"role": "user", "content": "Hello, write a simple Python function that adds two numbers."}
    ],
    "temperature": 0.7,
    "max_tokens": 100
}

print(f"\nTesting Together AI API...")
print(f"URL: {url}")
print(f"Model: {payload['model']}")
print(f"Payload: {json.dumps(payload, indent=2)}")

try:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, headers=headers, json=payload)
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response: {response.text[:500]}")

        if response.status_code == 200:
            data = response.json()
            print(f"\n✓ Success!")
            print(f"Content: {data['choices'][0]['message']['content'][:200]}")
        else:
            print(f"\n✗ Error: {response.status_code}")
            response.raise_for_status()

except Exception as e:
    print(f"\n✗ Exception: {e}")
    import traceback
    traceback.print_exc()
