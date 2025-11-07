# RunPod vLLM Troubleshooting Guide

## Current Status

**Port 35303**: Health endpoint responds (200 OK) but completions endpoint returns 405 Not Allowed
**Ports 35304, 35305**: Not responding at all

## Problem

Nginx on RunPod is blocking POST requests to `/v1/completions`. This is a common issue with RunPod's default nginx configuration.

## Diagnostic Results

```bash
# Health check - WORKS
curl http://213.173.102.138:35303/health
# Returns: 200 OK

# Completion request - BLOCKED
curl -X POST http://213.173.102.138:35303/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "...", "prompt": "test", "max_tokens": 10}'
# Returns: 405 Not Allowed from nginx
```

## Solutions

### Option 1: Fix nginx Configuration (Recommended)

SSH into your RunPod instance and update nginx config:

```bash
ssh root@213.173.102.138 -p 22

# Check if vLLM is running
ps aux | grep vllm

# Check nginx config
cat /etc/nginx/sites-enabled/default

# You need to ensure nginx is proxying POST requests to vLLM
# The config should have something like:

location /v1 {
    proxy_pass http://127.0.0.1:8001;  # or 8002, 8003
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

    # IMPORTANT: Allow POST
    limit_except GET POST {
        deny all;
    }
}

# After editing, reload nginx
sudo nginx -t  # Test config
sudo systemctl reload nginx
```

### Option 2: Use RunPod's Direct Port Mapping

Instead of using nginx proxy, expose vLLM ports directly:

1. In RunPod web interface, go to your pod settings
2. Under "Exposed Ports", map internal ports directly:
   - Internal 8001 → External (auto-assigned)
   - Internal 8002 → External (auto-assigned)
   - Internal 8003 → External (auto-assigned)
3. Note the external port numbers
4. Update `demo_autonomous_tdd_runpod.py` with those ports

### Option 3: Run vLLM Without nginx

Start vLLM servers without going through nginx:

```bash
# On RunPod instance
# Kill existing vLLM
pkill -f vllm

# Start servers with host 0.0.0.0 to accept external connections
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-Coder-1.5B-Instruct \
    --port 8001 \
    --host 0.0.0.0 \
    --gpu-memory-utilization 0.85 \
    --max-model-len 4096 \
    --dtype auto \
    --trust-remote-code \
    > /tmp/vllm_8001.log 2>&1 &

# Repeat for other models on ports 8002, 8003
```

Then in RunPod settings, map these ports directly without nginx.

### Option 4: Use Local Ollama Instead (Fallback)

If RunPod configuration is difficult, we can test ensemble learning locally:

```bash
# Use local Ollama models
cd /home/ch_dev/ace_enterprise
python demo_ensemble_local.py
```

This uses local models instead of GPU-accelerated vLLM, but validates the ensemble learning bug fixes.

## Verification Commands

Once you've applied a fix, test with:

```bash
# Test from local machine
curl -X POST http://213.173.102.138:35303/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "prompt": "def hello():",
    "max_tokens": 20,
    "temperature": 0.7
  }'

# Should return JSON with completion, not 405 error
```

## Next Steps

1. **Try Option 1 or 2** - These are the best for GPU acceleration
2. **If blocked, use Option 4** - Test locally to verify bug fixes work
3. **Report back** - Once vLLM is accessible, run the RunPod demo

## RunPod-Specific Notes

- RunPod uses nginx by default to proxy HTTP traffic
- The default nginx config may not allow POST to all endpoints
- Health checks often work because they're GET requests
- You may need to edit `/etc/nginx/sites-enabled/default` or similar

## Contact

If you continue to have issues, check:
- RunPod documentation on exposing custom services
- RunPod community forums
- Or run the local ensemble demo instead
