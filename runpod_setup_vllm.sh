#!/bin/bash
# RunPod vLLM Setup Script
# Run this on your RunPod instance to start 3 vLLM servers

set -e

echo "============================================================"
echo "  RunPod vLLM Setup for ACE Ensemble Learning"
echo "============================================================"

# Configuration - 7B Models for Better Quality
# RTX 4090 has 24GB VRAM - can easily fit 3x 7B models (~12GB total)
MODEL1="Qwen/Qwen2.5-Coder-7B-Instruct"    # Best coding model (~4GB)
MODEL2="Qwen/Qwen2.5-7B-Instruct"          # General purpose (~4GB)
MODEL3="deepseek-ai/deepseek-coder-6.7b-instruct"  # Alternative coder (~4GB)

PORT1=8001
PORT2=8002
PORT3=8003

GPU_MEMORY_UTILIZATION=0.85
MAX_MODEL_LEN=4096

echo ""
echo "Models to deploy:"
echo "  1. $MODEL1 (port $PORT1)"
echo "  2. $MODEL2 (port $PORT2)"
echo "  3. $MODEL3 (port $PORT3)"
echo ""

# Check if vLLM is installed
if ! command -v vllm &> /dev/null; then
    echo "❌ vLLM not found. Installing..."
    pip install vllm
fi

# Check GPU availability
if ! nvidia-smi &> /dev/null; then
    echo "❌ No GPU detected! This script requires NVIDIA GPU."
    exit 1
fi

nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
echo ""

# Kill existing vLLM processes
echo "Checking for existing vLLM processes..."
pkill -f "vllm.entrypoints.openai.api_server" || true
sleep 2

# Function to start vLLM server
start_vllm() {
    local model=$1
    local port=$2
    local gpu=$3
    local log_file="/tmp/vllm_${port}.log"

    echo "Starting vLLM server:"
    echo "  Model: $model"
    echo "  Port: $port"
    echo "  GPU: $gpu"
    echo "  Log: $log_file"

    CUDA_VISIBLE_DEVICES=$gpu nohup python -m vllm.entrypoints.openai.api_server \
        --model "$model" \
        --port $port \
        --host 0.0.0.0 \
        --gpu-memory-utilization $GPU_MEMORY_UTILIZATION \
        --max-model-len $MAX_MODEL_LEN \
        --dtype auto \
        --trust-remote-code \
        > "$log_file" 2>&1 &

    echo "  PID: $!"
    echo ""
}

# Start servers on single GPU (RTX 4090 has enough VRAM for all 3)
echo "Starting vLLM servers..."
start_vllm "$MODEL1" $PORT1 0
sleep 5  # Stagger starts to avoid race conditions

start_vllm "$MODEL2" $PORT2 0
sleep 5

start_vllm "$MODEL3" $PORT3 0

echo ""
echo "============================================================"
echo "Waiting for servers to initialize..."
echo "============================================================"
echo ""

# Wait for servers to be ready
wait_for_server() {
    local port=$1
    local max_attempts=60
    local attempt=1

    echo "Waiting for server on port $port..."

    while [ $attempt -le $max_attempts ]; do
        if curl -s http://localhost:$port/health > /dev/null 2>&1; then
            echo "✓ Server on port $port is ready!"
            return 0
        fi
        echo "  Attempt $attempt/$max_attempts..."
        sleep 5
        attempt=$((attempt + 1))
    done

    echo "✗ Server on port $port failed to start"
    echo "  Check log: /tmp/vllm_${port}.log"
    return 1
}

wait_for_server $PORT1
wait_for_server $PORT2
wait_for_server $PORT3

echo ""
echo "============================================================"
echo "✅ All vLLM servers are running!"
echo "============================================================"
echo ""
echo "Endpoints:"
echo "  Model 1: http://0.0.0.0:$PORT1/v1/completions"
echo "  Model 2: http://0.0.0.0:$PORT2/v1/completions"
echo "  Model 3: http://0.0.0.0:$PORT3/v1/completions"
echo ""
echo "Logs:"
echo "  tail -f /tmp/vllm_8001.log"
echo "  tail -f /tmp/vllm_8002.log"
echo "  tail -f /tmp/vllm_8003.log"
echo ""
echo "To test:"
echo '  curl -X POST http://localhost:8001/v1/completions \'
echo '    -H "Content-Type: application/json" \'
echo '    -d '"'"'{"model": "'"$MODEL1"'", "prompt": "def hello():", "max_tokens": 50}'"'"''
echo ""
echo "To expose ports on RunPod:"
echo "  1. Go to RunPod pod settings"
echo "  2. Expose TCP ports: 8001, 8002, 8003"
echo "  3. Note the external port mappings"
echo ""
