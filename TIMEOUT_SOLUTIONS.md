# Ollama Model Timeout Solutions

## Problem
The qwen3-coder:30b model (18 GB) is timing out after 60 seconds because it's:
- Running primarily on CPU (86%) with minimal GPU acceleration (14%)
- Very large model requiring significant computation time
- Taking 58+ seconds to generate responses

## Current Status
- **Model loaded**: qwen3-coder:30b (19 GB in memory)
- **Current timeout**: 60 seconds (src/utils/llm_client.py:42)
- **Available alternatives**: deepseek-coder:6.7b (3.8 GB), qwen3:1.7b (1.4 GB)

## Solutions

### Solution 1: Switch to Faster Model (Recommended)

**Use deepseek-coder:6.7b instead - it responds in ~11 seconds**

```bash
# Option A: Update .env file
sed -i 's/OLLAMA_DEFAULT_MODEL=qwen3-coder:30b/OLLAMA_DEFAULT_MODEL=deepseek-coder:6.7b/' .env

# Option B: Or set environment variable
export OLLAMA_DEFAULT_MODEL=deepseek-coder:6.7b

# Then restart services
make restart  # or manually restart uvicorn
```

**Pros:**
- ✓ Faster responses (~11s vs 60+s)
- ✓ Less resource intensive (3.8 GB vs 18 GB)
- ✓ Still excellent for coding tasks
- ✓ Better GPU utilization
- ✓ No code changes needed

**Cons:**
- ✗ Slightly lower quality than 30B model
- ✗ Smaller context window

### Solution 2: Increase Timeout for Large Model

**Keep qwen3-coder:30b but allow more time**

Edit `src/utils/llm_client.py`:

```python
# Line 42 - change from:
self.timeout = 60.0  # seconds

# To:
self.timeout = 180.0  # seconds (3 minutes)
```

**Pros:**
- ✓ Highest quality responses
- ✓ Largest context window
- ✓ Simple fix

**Cons:**
- ✗ Slow user experience (60-180s per response)
- ✗ High resource usage
- ✗ May still timeout on complex prompts

### Solution 3: Use Smallest Model

**Switch to qwen3:1.7b for maximum speed**

```bash
# Update .env
export OLLAMA_DEFAULT_MODEL=qwen3:1.7b
```

**Pros:**
- ✓ Fastest responses (<5s)
- ✓ Minimal resource usage

**Cons:**
- ✗ Lower quality
- ✗ May struggle with complex tasks

### Solution 4: Hybrid Approach

**Use different models for different components**

```python
# In demo_ace_loop.py or other scripts
fast_client = LLMClient(model="deepseek-coder:6.7b")  # For Generator
quality_client = LLMClient(model="qwen3-coder:30b")   # For Reflector/Curator

generator = Generator(playbook_manager, fast_client)
reflector = Reflector(quality_client)
curator = Curator(playbook_manager, quality_client)
```

## Performance Comparison

| Model              | Size   | Response Time | Quality | Best For             |
|--------------------|--------|---------------|---------|----------------------|
| qwen3-coder:30b    | 18 GB  | 60-180s       | ★★★★★   | Complex analysis     |
| deepseek-coder:6.7b| 3.8 GB | ~11s          | ★★★★☆   | **General use (Recommended)** |
| qwen3:1.7b         | 1.4 GB | <5s           | ★★★☆☆   | Simple/fast tasks    |

## Recommendation

**Use Solution 1 (switch to deepseek-coder:6.7b)** because:
1. 5x faster than current setup
2. Still maintains good quality for ACE learning loop
3. Better resource efficiency
4. No timeout issues
5. Proven to work (tested: 11s response time)

## Quick Fix Commands

```bash
# Recommended: Switch to deepseek-coder:6.7b
echo "OLLAMA_DEFAULT_MODEL=deepseek-coder:6.7b" >> .env
source .env

# Restart API to pick up new model
pkill -f uvicorn
source venv/bin/activate && python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 &

# Test the change
python demo_ace_loop.py
```

## Long-term Solution

Consider implementing **adaptive timeout** based on model size:

```python
# In src/utils/llm_client.py
def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
    self.provider = provider or settings.default_llm_provider
    self.model = self._get_default_model(model)
    
    # Adaptive timeout based on model size
    if "30b" in self.model.lower() or "32b" in self.model.lower():
        self.timeout = 180.0
    elif "7b" in self.model.lower() or "8b" in self.model.lower():
        self.timeout = 60.0
    else:
        self.timeout = 30.0
```
