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
3. **Select GPU**: Choose **RTX 4090** (recommended for cost/performance)
4. **Choose Pod Type**: Select **Spot** (60-80% cheaper)
5. **Select Template**: Choose **RunPod PyTorch** or **vLLM** template
6. **Configure**:
   - Container Disk: 50GB minimum
   - Volume: Optional (for persistent storage)
   - Expose Ports: 8001, 8002, 8003
7. **Deploy** the pod

### 2. Install vLLM

Once pod starts, open **Terminal** and run:

```bash
# Update pip
pip install --upgrade pip

# Install vLLM
pip install vllm

# Verify installation
vllm --version
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
# Navigate to workspace
cd /workspace

# If using git clone:
cd ace_enterprise/scripts

# Make scripts executable (if not already)
chmod +x start_vllm_multi.sh auto_shutdown.sh

# Start all 3 models
./start_vllm_multi.sh
```

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

Get your pod's **Public IP** from RunPod dashboard, then test:

```bash
# Replace <POD_IP> with your actual pod IP
curl http://<POD_IP>:8001/health
curl http://<POD_IP>:8002/health
curl http://<POD_IP>:8003/health
```

All should return: `{"status":"ok"}`

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

In your local ACE Enterprise project, update the vLLM endpoints:

```python
# In demo_ensemble_learning.py or config
RUNPOD_IP = "123.45.67.89"  # Replace with your pod IP

# Update models to use vLLM via HTTP
models = [
    ("vllm", f"http://{RUNPOD_IP}:8001", "qwen2.5-coder:1.5b"),
    ("vllm", f"http://{RUNPOD_IP}:8002", "qwen2.5:1.5b"),
    ("vllm", f"http://{RUNPOD_IP}:8003", "qwen2.5-coder:0.5b"),
]
```

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

### Models Won't Start
```bash
# Check logs
tail -f /workspace/logs/*.log

# Common issues:
# 1. Not enough VRAM: Reduce GPU_MEMORY_PER_MODEL in script
# 2. Port already in use: pkill -f vllm, then restart
# 3. Model not downloaded: vLLM will auto-download (takes time)
```

### Port Already in Use
```bash
# Kill everything on port 8001
lsof -ti:8001 | xargs kill -9

# Or kill all vLLM processes
pkill -f vllm
```

### Can't Connect from Local Machine
1. Check pod is running (RunPod dashboard)
2. Verify ports are exposed (8001, 8002, 8003)
3. Check firewall rules
4. Try pod's internal IP first: `curl http://localhost:8001/health`

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
