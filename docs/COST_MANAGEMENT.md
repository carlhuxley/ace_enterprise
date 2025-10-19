# RunPod Cost Management Guide for ACE Ensemble Learning

## Billing Info
- **RunPod GPU Pods**: You are charged for every second the pod is running, even when idle
- **No inference ≠ No cost**: The pod continues charging even with 0 requests
- **Multiple models**: Running 3 vLLM instances uses same GPU, same cost as 1 model

## Cost-Saving Options

### Option 1: Manual Stop/Start (Cheapest)
**Best for**: Predictable usage patterns, development work

1. **Stop the pod** when not in use:
   - Go to RunPod dashboard
   - Click "Stop" on your pod
   - Charges pause immediately
   
2. **Start when needed**:
   - Click "Start" 
   - Wait ~2-5 minutes for models to load
   - Resume work

**Pros**: Pay only for actual usage time
**Cons**: Manual process, startup delay

### Option 2: Use Spot Instances (Up to 80% cheaper)
**Best for**: Non-critical workloads that can handle interruptions

- RunPod offers "Spot" instances that are much cheaper
- Can be interrupted if demand is high
- Great for development/testing

### Option 3: Auto-shutdown Script
**Best for**: Preventing accidental overnight charges

Save this as `/workspace/auto_shutdown.sh`:

```bash
#!/bin/bash
# Auto-shutdown after X minutes of inactivity for ACE Ensemble

IDLE_MINUTES=30  # Shutdown after 30 mins idle
CHECK_INTERVAL=300  # Check every 5 minutes
IDLE_COUNT=0
REQUIRED_IDLE_CHECKS=$((IDLE_MINUTES / (CHECK_INTERVAL / 60)))

echo "Auto-shutdown monitor started"
echo "Will shutdown after $IDLE_MINUTES minutes of inactivity"

while true; do
  # Check if any models are actively processing
  ACTIVE=0

  for port in 8001 8002 8003; do
    # Check vLLM metrics endpoint for active requests
    METRICS=$(curl -s http://localhost:$port/metrics 2>/dev/null || echo "")

    if echo "$METRICS" | grep -q "vllm:num_requests_running"; then
      RUNNING=$(echo "$METRICS" | grep "vllm:num_requests_running" | awk '{print $2}')
      if [ "$RUNNING" -gt 0 ]; then
        ACTIVE=1
        break
      fi
    fi
  done

  if [ $ACTIVE -eq 1 ]; then
    IDLE_COUNT=0
    echo "[$(date)] Activity detected - resetting idle timer"
  else
    IDLE_COUNT=$((IDLE_COUNT + 1))
    MINUTES_IDLE=$((IDLE_COUNT * CHECK_INTERVAL / 60))
    echo "[$(date)] No activity - idle for $MINUTES_IDLE minutes"

    if [ $IDLE_COUNT -ge $REQUIRED_IDLE_CHECKS ]; then
      echo "[$(date)] Idle threshold reached - shutting down vLLM models"
      pkill -f vllm
      echo "Models stopped. You can manually stop the pod in RunPod dashboard."
      echo "Or install runpodctl for automatic pod shutdown."
      exit 0
    fi
  fi

  sleep $CHECK_INTERVAL
done
```

To enable:
```bash
chmod +x /workspace/auto_shutdown.sh
nohup /workspace/auto_shutdown.sh > /workspace/logs/autoshutdown.log 2>&1 &
```

### Option 4: Use RunPod Serverless (Pay per inference)
**Best for**: Sporadic usage with unpredictable patterns

- Only pay for actual inference time
- Cold starts (~10-20 seconds)
- More expensive per-minute, but $0 when idle

## Recommended Approach for ACE Ensemble

**For Development/Testing (Recommended):**
1. Use **Spot instances** (RTX 4090 recommended)
2. Enable **auto-shutdown script** (30-minute idle timeout)
3. **Manually stop** pod at end of work session
4. Estimated cost: **$40-80/month** (4-8 hours/day usage)

**For Production:**
1. Start with **Spot** instance (interruptions are rare)
2. Monitor for 1-2 weeks to assess reliability
3. Upgrade to **Secure** if interruptions occur
4. Use auto-shutdown as safety net

**Why Spot Works for Ensemble:**
- 3 small models load quickly (~2-3 minutes)
- Interruptions are rare for development hours
- 60-80% cost savings vs secure instances
- State is saved in your playbook database

## Cost Estimation Examples

### GPU Options for 3-Model Ensemble:
| GPU | VRAM | Spot Price | Secure Price | Monthly (Spot, 8h/day) |
|-----|------|------------|--------------|------------------------|
| RTX 4090 | 24GB | $0.29/hr | $0.49/hr | **$70/month** ✓ Recommended |
| RTX 3090 | 24GB | $0.24/hr | $0.44/hr | $58/month |
| RTX A6000 | 48GB | $0.69/hr | $1.29/hr | $166/month (overkill) |

**Your Use Case (Development):**
- RTX 4090 Spot: $0.29/hour
- 8 hours/day × 30 days = 240 hours/month
- **Total: $70/month**

With auto-shutdown safety net:
- Forgot to stop once (10 extra hours): $73/month
- Without safety net (24/7 by accident): $209/month 💸

## Connecting ACE to vLLM on RunPod

### 1. Get RunPod Pod IP
After starting your pod:
1. Go to RunPod dashboard
2. Click on your pod
3. Note the **Public IP** or **TCP Port Mappings**

### 2. Update ACE Configuration
Create or update `src/config/vllm_endpoints.py`:

```python
# vLLM endpoints on RunPod
VLLM_ENDPOINTS = {
    "vllm": {
        "base_url": "http://<RUNPOD_IP>",  # Replace with your pod IP
        "models": {
            "qwen2.5-coder:1.5b": {
                "url": "http://<RUNPOD_IP>:8001/v1",
                "model_name": "Qwen/Qwen2.5-Coder-1.5B-Instruct"
            },
            "qwen2.5:1.5b": {
                "url": "http://<RUNPOD_IP>:8002/v1",
                "model_name": "Qwen/Qwen2.5-1.5B-Instruct"
            },
            "qwen2.5-coder:0.5b": {
                "url": "http://<RUNPOD_IP>:8003/v1",
                "model_name": "Qwen/Qwen2.5-Coder-0.5B-Instruct"
            }
        }
    }
}
```

### 3. Update Ensemble Learner
In `demo_ensemble_learning.py`:

```python
# Update models to use vLLM endpoints
models = [
    ("vllm", "qwen2.5-coder:1.5b"),
    ("vllm", "qwen2.5:1.5b"),
    ("vllm", "qwen2.5-coder:0.5b"),
]
```

### 4. Test Connection
```bash
# From your local machine
curl http://<RUNPOD_IP>:8001/health

# Test inference
curl -X POST http://<RUNPOD_IP>:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen/Qwen2.5-Coder-1.5B-Instruct", "prompt": "def hello():", "max_tokens": 50}'
```

## Quick Commands

**Start all models:**
```bash
bash /workspace/start_vllm_multi.sh
```

**Enable auto-shutdown:**
```bash
chmod +x /workspace/auto_shutdown.sh
nohup /workspace/auto_shutdown.sh > /workspace/logs/autoshutdown.log 2>&1 &
```

**Monitor activity:**
```bash
# Check GPU usage
nvidia-smi

# Check vLLM processes
ps aux | grep vllm

# Check active requests
curl -s http://localhost:8001/metrics | grep num_requests_running
```

**Stop everything:**
```bash
# Stop vLLM models
pkill -f vllm

# Stop auto-shutdown monitor
pkill -f auto_shutdown

# Stop all logging
pkill -f "tail -f"
```

**View logs:**
```bash
# All model logs
tail -f /workspace/logs/*.log

# Specific model
tail -f /workspace/logs/qwen-coder-1.5b.log

# Auto-shutdown log
tail -f /workspace/logs/autoshutdown.log
```