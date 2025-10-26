# RunPod Setup Guide for ACE Ensemble Learning

This guide will help you deploy 3 vLLM models on RunPod for ACE Ensemble Learning.

## Prerequisites

- RunPod account with payment method
- Basic understanding of Docker/Linux commands
- Your ACE Enterprise code ready

## Step-by-Step Setup

### 1. Create RunPod Pod

1. **Go to RunPod.io** and sign in
2. **Click "Deploy"** → "GPU Pods"
3. **Select GPU**:
   - **⚠️ CRITICAL:** Choose **at least 1 GPU** - this is REQUIRED!
   - Recommended: **RTX 4090** (24GB VRAM, good cost/performance)
   - **❌ DO NOT select "0 GPU"** - this creates a transfer-only pod with only ~500MB RAM
   - With 0 GPU, you'll get "fork: Cannot allocate memory" errors
4. **Choose Pod Type**: Select **Spot** (60-80% cheaper)
5. **Select Template**:
   - Recommended: **vLLM** template (vLLM pre-installed)
   - Alternative: **RunPod PyTorch** (requires manual vLLM installation)
6. **Configure**:
   - Container Disk: 50GB minimum
   - Volume: Optional (for persistent storage)
   - Expose Ports: 8001, 8002, 8003
7. **Deploy** the pod

**⚠️ Common Mistake - 0 GPU Mode:**
If you accidentally create a pod with 0 GPU:
- Symptoms: ~488MB RAM, `nvidia-smi` shows no GPUs, "Cannot allocate memory" errors
- This is "transfer mode" - designed only for accessing files, not compute
- Solution: Stop the pod and create a new one with **at least 1 GPU** selected

### 2. Verify/Install vLLM

Once pod starts, open **Terminal** and verify vLLM is available:

```bash
# Check if vLLM is already installed (should be if using vllm_latest template)
vllm --version
```

**If vLLM is already installed:** Skip to Step 3.

**If vLLM is NOT installed** (you'll get "command not found"), install it manually:

**IMPORTANT:** RunPod's container disk (overlay fs) is typically only 5-10GB. To avoid "No space left on device" errors, we'll install vLLM in `/workspace` which has much more space.

```bash
# Navigate to /workspace (has plenty of space)
cd /workspace

# Set environment variables to use /workspace for cache/temp
export TMPDIR=/workspace/tmp
export PIP_CACHE_DIR=/workspace/pip_cache
export HF_HOME=/workspace/huggingface

# Create directories
mkdir -p $TMPDIR $PIP_CACHE_DIR $HF_HOME

# Create Python virtual environment in /workspace
python3 -m venv vllm_env

# Activate the virtual environment
source /workspace/vllm_env/bin/activate

# Install vLLM (this may take 5-10 minutes)
pip install --upgrade pip
pip install --no-cache-dir vllm

# Verify installation
vllm --version
```

**Note:**
- You'll see warnings about `TRANSFORMERS_CACHE` and `UnspecifiedPlatform` - these are normal and harmless.
- If you manually installed vLLM in a venv, activate it every time you start a new terminal:
  ```bash
  source /workspace/vllm_env/bin/activate
  ```

### 3. Upload Scripts

Upload these files to `/workspace/`:

**Option A: Git Clone (Recommended)**
```bash
cd /workspace
git clone https://github.com/YOUR_USERNAME/ace_enterprise.git
cd ace_enterprise
```

**Option B: Manual Upload**
1. Go to RunPod **Files** tab
2. Upload `scripts/start_vllm_multi.sh`
3. Upload `scripts/auto_shutdown.sh`

### 4. Start Models

```bash
# If you manually installed vLLM in venv, activate it first:
# source /workspace/vllm_env/bin/activate

# Navigate to scripts directory
cd /workspace/ace_enterprise/scripts

# Make scripts executable (if not already)
chmod +x start_vllm_multi.sh auto_shutdown.sh

# Start all 3 models
./start_vllm_multi.sh
```

**Note:** If using the vllm_latest template, vLLM should already be in your PATH and you don't need to activate a venv.

**Expected output:**
```
Starting ACE Ensemble Learning vLLM setup...
Starting Model 1: Qwen2.5-Coder-1.5B on port 8001...
Starting Model 2: Qwen2.5-1.5B on port 8002...
Starting Model 3: Qwen2.5-Coder-0.5B on port 8003...
Waiting for models to initialize...
```

Wait 2-3 minutes for models to load. You'll see:
```
========================================
ACE Ensemble Learning - All models ready!
========================================
✓ Model on port 8001 is healthy
✓ Model on port 8002 is healthy
✓ Model on port 8003 is healthy
```

### 5. Enable Auto-Shutdown (Optional but Recommended)

In a **new terminal** (don't close the model terminal):

```bash
cd /workspace
# If using git clone:
cd ace_enterprise/scripts

# Start auto-shutdown monitor
nohup ./auto_shutdown.sh > /workspace/logs/autoshutdown.log 2>&1 &

# Verify it's running
tail -f /workspace/logs/autoshutdown.log
```

Press `Ctrl+C` to exit log viewing (monitor keeps running).

### 6. Test Models

**Important:** RunPod uses **port mapping**. Your pod exposes different external ports than the internal ports.

Check your pod's port mapping in the RunPod dashboard (typically shows something like):
- Internal 8001 → External 33186
- Internal 8002 → External 33187
- Internal 8003 → External 33188

Get your pod's **Public IP** and **external ports** from RunPod dashboard.

**Test locally on RunPod first:**
```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

All should return: `{"status":"ok"}` or similar success message.

**Test from your local machine:**
```bash
# Replace <POD_IP> and <EXTERNAL_PORT> with your actual values
curl http://<POD_IP>:<EXTERNAL_PORT_8001>/health
curl http://<POD_IP>:<EXTERNAL_PORT_8002>/health
curl http://<POD_IP>:<EXTERNAL_PORT_8003>/health
```

Example (with actual port mapping):
```bash
curl http://103.196.86.55:33186/health
curl http://103.196.86.55:33187/health
curl http://103.196.86.55:33188/health
```

### 7. Test Inference

```bash
curl -X POST http://<POD_IP>:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "prompt": "def fibonacci(n):",
    "max_tokens": 100,
    "temperature": 0.7
  }'
```

You should get a JSON response with generated code.

## Connecting to ACE Enterprise

### Update Local Configuration

In your local ACE Enterprise project, update the vLLM endpoints with **external ports**:

```python
# In demo_ensemble_learning.py
# Replace with your actual pod IP and external port mappings
RUNPOD_IP = "103.196.86.55"

# Port mapping (internal:external) - check your RunPod dashboard
# 8001 -> 33186
# 8002 -> 33187
# 8003 -> 33188

# Update models to use vLLM via HTTP (use EXTERNAL ports)
models = [
    ("vllm", "Qwen/Qwen2.5-Coder-1.5B-Instruct", f"http://{RUNPOD_IP}:33186"),
    ("vllm", "Qwen/Qwen2.5-1.5B-Instruct", f"http://{RUNPOD_IP}:33187"),
    ("vllm", "Qwen/Qwen2.5-Coder-0.5B-Instruct", f"http://{RUNPOD_IP}:33188"),
]
```

The configuration is already set up in `demo_ensemble_learning.py` - just update the IP and port numbers to match your pod.

### Update LLM Client

Modify `src/utils/llm_client.py` to support vLLM endpoints:

```python
def _generate_vllm(self, prompt, system_prompt, max_tokens, temperature):
    """Generate using vLLM API (OpenAI-compatible)."""
    url = f"{self.base_url}/v1/completions"

    payload = {
        "model": self.model,
        "prompt": prompt,
        "max_tokens": max_tokens or 1024,
        "temperature": temperature,
    }

    if system_prompt:
        # vLLM doesn't support system prompts in completions
        # Prepend to prompt instead
        payload["prompt"] = f"{system_prompt}\n\n{prompt}"

    response = httpx.post(url, json=payload, timeout=self.timeout)
    response.raise_for_status()
    data = response.json()

    return {
        "content": data["choices"][0]["text"],
        "tokens_used": data["usage"]["total_tokens"],
    }
```

## Monitoring & Maintenance

### Check GPU Usage
```bash
nvidia-smi
```

### Monitor Logs
```bash
# All models
tail -f /workspace/logs/*.log

# Specific model
tail -f /workspace/logs/qwen-coder-1.5b.log

# Auto-shutdown monitor
tail -f /workspace/logs/autoshutdown.log
```

### Check Active Requests
```bash
curl http://localhost:8001/metrics | grep num_requests_running
```

### Restart Models
```bash
# Stop all models
pkill -f vllm

# Wait a few seconds
sleep 5

# Restart
cd /workspace/ace_enterprise/scripts
./start_vllm_multi.sh
```

## Cost Management

### When Finished Working

**IMPORTANT**: Always stop your pod when done!

1. **Stop auto-shutdown** (if running):
   ```bash
   pkill -f auto_shutdown
   ```

2. **Stop models**:
   ```bash
   pkill -f vllm
   ```

3. **Stop Pod** in RunPod dashboard:
   - Go to RunPod dashboard
   - Click your pod
   - Click **"Stop"**
   - Confirm

### Cost Estimates

**RTX 4090 Spot Instance:**
- $0.29/hour
- 8 hours/day × 30 days = **$70/month**
- Left running 24/7 = **$209/month** ⚠️

**Auto-Shutdown Benefits:**
- Forgot to stop once (10 extra hours): $73/month
- Without safety net: $209/month
- **Savings: $136/month!**

## Troubleshooting

### "No space left on device" Error
This happens because RunPod's container disk (overlay fs) is only 5-10GB.

**Solution:** Install vLLM in `/workspace` using a virtual environment (see Step 2 above).

```bash
# Clean up and reinstall
cd /workspace
rm -rf vllm_env pip_cache tmp

# Set environment variables
export TMPDIR=/workspace/tmp
export PIP_CACHE_DIR=/workspace/pip_cache
export HF_HOME=/workspace/huggingface
mkdir -p $TMPDIR $PIP_CACHE_DIR $HF_HOME

# Create venv and install
python3 -m venv vllm_env
source /workspace/vllm_env/bin/activate
pip install --no-cache-dir vllm
```

### "vllm: command not found"
**Solution 1:** Make sure you selected the **vllm_latest** template when creating the pod.

**Solution 2:** If you used a different template, activate the virtual environment:
```bash
source /workspace/vllm_env/bin/activate
vllm --version  # Should work now
```

### "fork: Cannot allocate memory"
This error means the pod doesn't have enough system RAM.

**Root Cause #1 (Most Common):** Pod created with **0 GPU** selected
- 0-GPU pods are "transfer mode" with only ~488MB RAM
- Check with: `nvidia-smi` (should show at least 1 GPU)
- Check RAM: `free -h` (should show 30GB+, not 488MB)
- **Solution:** Stop pod and create new one with **at least 1 GPU**

**Root Cause #2 (Rare):** Pod has GPU but insufficient RAM for 3 models
- Happens if pod has <16GB system RAM
- **Solutions:**
  1. Use a larger GPU instance (more VRAM usually = more system RAM)
  2. Start models sequentially instead of simultaneously
  3. Use fewer models (2 instead of 3)

**Quick Check:**
```bash
# Verify you have a GPU
nvidia-smi

# Check system RAM
free -h
# Should show ~30GB total, not 488MB

# If you see 488MB and no GPU: You're in 0-GPU transfer mode!
```

### Models Won't Start
```bash
# Check if vLLM processes are running
ps aux | grep vllm | grep -v grep

# Check logs for errors
tail -f /workspace/logs/*.log

# Common issues:
# 1. venv not activated: source /workspace/vllm_env/bin/activate
# 2. Not enough VRAM: Reduce GPU_MEMORY_PER_MODEL in script
# 3. Port already in use: pkill -f vllm, then restart
# 4. Model not downloaded: vLLM will auto-download (takes time)
```

### Port Already in Use
```bash
# Kill everything on port 8001
lsof -ti:8001 | xargs kill -9

# Or kill all vLLM processes
pkill -f vllm
```

### Can't Connect from Local Machine
1. **Check pod is running** (RunPod dashboard - should be green)
2. **Verify ports are exposed** (8001, 8002, 8003 in pod settings)
3. **Use external ports**, not internal ones:
   - Check RunPod dashboard for port mapping (e.g., 8001→33186)
   - Update your local config with external ports
4. **Test locally first on RunPod**: `curl http://localhost:8001/health`
5. **Check if vLLM is running**: `ps aux | grep vllm`
6. **Check logs**: `tail -f /workspace/logs/*.log`

### Getting 502 Bad Gateway
This means the port is exposed but vLLM isn't running:

```bash
# Activate venv
source /workspace/vllm_env/bin/activate

# Check if vLLM is running
ps aux | grep vllm | grep -v grep

# If not running, start models
cd /workspace/ace_enterprise/scripts
./start_vllm_multi.sh

# Wait 2-3 minutes, then test
curl http://localhost:8001/health
```

### Models Running Slow
- Check GPU usage: `nvidia-smi`
- If GPU at 100%: Models might be too large for GPU
- Reduce `GPU_MEMORY_PER_MODEL` or use smaller models

## Next Steps

1. **Test Ensemble Learning**: Run `python demo_ensemble_learning.py` locally
2. **Monitor Costs**: Check RunPod billing daily for first week
3. **Optimize**: Adjust idle timeout based on your usage patterns
4. **Scale**: Add more models or upgrade GPU if needed

## Quick Reference

| Command | Description |
|---------|-------------|
| `./start_vllm_multi.sh` | Start all models |
| `pkill -f vllm` | Stop all models |
| `nvidia-smi` | Check GPU usage |
| `tail -f /workspace/logs/*.log` | View all logs |
| `curl localhost:8001/health` | Test model health |

## Support

- **RunPod Docs**: https://docs.runpod.io/
- **vLLM Docs**: https://docs.vllm.ai/
- **ACE Issues**: https://github.com/YOUR_USERNAME/ace_enterprise/issues
