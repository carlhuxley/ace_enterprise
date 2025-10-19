#!/bin/bash

# Startup script for running 3 vLLM instances for ACE Ensemble Learning
# Each model runs on a separate port with limited GPU memory allocation
# Optimized for small models (0.5b - 1.5b parameters)

set -e

echo "Starting ACE Ensemble Learning vLLM setup..."

# Configuration
export CUDA_VISIBLE_DEVICES=0
GPU_MEMORY_PER_MODEL=0.30  # 30% each = 90% total for 3 models
MAX_MODEL_LEN=4096  # Good for most ACE tasks
MAX_TOKENS=1024  # Limit response length
TENSOR_PARALLEL=1  # No tensor parallelism for small models

# Model paths - Optimized for ensemble learning with small, fast models
MODEL1="Qwen/Qwen2.5-Coder-1.5B-Instruct"  # Fast coding model
MODEL2="Qwen/Qwen2.5-1.5B-Instruct"        # General reasoning model
MODEL3="Qwen/Qwen2.5-Coder-0.5B-Instruct"  # Ultra-fast backup model

# Ports for each model
PORT1=8001  # qwen2.5-coder-1.5b
PORT2=8002  # qwen2.5-1.5b
PORT3=8003  # qwen2.5-coder-0.5b

# Create log directory
mkdir -p /workspace/logs

echo "Starting Model 1: Qwen2.5-Coder-1.5B on port $PORT1..."
vllm serve "$MODEL1" \
  --host 0.0.0.0 \
  --port $PORT1 \
  --gpu-memory-utilization $GPU_MEMORY_PER_MODEL \
  --max-model-len $MAX_MODEL_LEN \
  --max-num-seqs 256 \
  --tensor-parallel-size $TENSOR_PARALLEL \
  --trust-remote-code \
  > /workspace/logs/qwen-coder-1.5b.log 2>&1 &

echo "Starting Model 2: Qwen2.5-1.5B on port $PORT2..."
vllm serve "$MODEL2" \
  --host 0.0.0.0 \
  --port $PORT2 \
  --gpu-memory-utilization $GPU_MEMORY_PER_MODEL \
  --max-model-len $MAX_MODEL_LEN \
  --max-num-seqs 256 \
  --tensor-parallel-size $TENSOR_PARALLEL \
  --trust-remote-code \
  > /workspace/logs/qwen-1.5b.log 2>&1 &

echo "Starting Model 3: Qwen2.5-Coder-0.5B on port $PORT3..."
vllm serve "$MODEL3" \
  --host 0.0.0.0 \
  --port $PORT3 \
  --gpu-memory-utilization $GPU_MEMORY_PER_MODEL \
  --max-model-len $MAX_MODEL_LEN \
  --max-num-seqs 512 \
  --tensor-parallel-size $TENSOR_PARALLEL \
  --trust-remote-code \
  > /workspace/logs/qwen-coder-0.5b.log 2>&1 &

# Wait for all models to be ready
echo "Waiting for models to initialize..."
sleep 30

# Health check function
check_health() {
  local port=$1
  curl -s http://localhost:$port/health > /dev/null 2>&1
  return $?
}

# Check if all models are up
echo "Checking model health..."
for port in $PORT1 $PORT2 $PORT3; do
  if check_health $port; then
    echo "✓ Model on port $port is healthy"
  else
    echo "✗ Model on port $port failed to start - check /workspace/logs/"
  fi
done

echo ""
echo "=========================================="
echo "ACE Ensemble Learning - All models ready!"
echo "=========================================="
echo "Model 1: http://localhost:$PORT1  (Qwen2.5-Coder-1.5B)"
echo "Model 2: http://localhost:$PORT2  (Qwen2.5-1.5B)"
echo "Model 3: http://localhost:$PORT3  (Qwen2.5-Coder-0.5B)"
echo "=========================================="
echo "Logs available in /workspace/logs/"
echo ""
echo "🔌 To connect from ACE Enterprise:"
echo "Update .env or config to use vLLM endpoints:"
echo "  VLLM_BASE_URL_1=http://<runpod-ip>:$PORT1"
echo "  VLLM_BASE_URL_2=http://<runpod-ip>:$PORT2"
echo "  VLLM_BASE_URL_3=http://<runpod-ip>:$PORT3"
echo ""
echo "📊 Monitor GPU usage: nvidia-smi"
echo "🛑 Stop all models: pkill -f vllm"
echo ""

# Keep script running to prevent container exit
tail -f /dev/null