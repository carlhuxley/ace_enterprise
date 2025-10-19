#!/bin/bash
# Auto-shutdown after X minutes of inactivity for ACE Ensemble
# This prevents accidental overnight charges on RunPod

IDLE_MINUTES=30  # Shutdown after 30 mins idle
CHECK_INTERVAL=300  # Check every 5 minutes
IDLE_COUNT=0
REQUIRED_IDLE_CHECKS=$((IDLE_MINUTES / (CHECK_INTERVAL / 60)))

echo "=========================================="
echo "ACE Auto-Shutdown Monitor"
echo "=========================================="
echo "Started at: $(date)"
echo "Idle timeout: $IDLE_MINUTES minutes"
echo "Check interval: $((CHECK_INTERVAL / 60)) minutes"
echo "Monitoring ports: 8001, 8002, 8003"
echo "=========================================="
echo ""

while true; do
  # Check if any models are actively processing
  ACTIVE=0
  TOTAL_REQUESTS=0

  for port in 8001 8002 8003; do
    # Check vLLM metrics endpoint for active requests
    METRICS=$(curl -s http://localhost:$port/metrics 2>/dev/null || echo "")

    if echo "$METRICS" | grep -q "vllm:num_requests_running"; then
      RUNNING=$(echo "$METRICS" | grep "vllm:num_requests_running" | awk '{print $2}')
      TOTAL_REQUESTS=$((TOTAL_REQUESTS + RUNNING))

      if [ "$RUNNING" -gt 0 ]; then
        ACTIVE=1
        echo "[$(date)] Port $port: $RUNNING active requests"
      fi
    fi
  done

  if [ $ACTIVE -eq 1 ]; then
    IDLE_COUNT=0
    echo "[$(date)] ✓ Activity detected ($TOTAL_REQUESTS requests) - resetting idle timer"
  else
    IDLE_COUNT=$((IDLE_COUNT + 1))
    MINUTES_IDLE=$((IDLE_COUNT * CHECK_INTERVAL / 60))
    REMAINING=$((IDLE_MINUTES - MINUTES_IDLE))

    echo "[$(date)] ⏰ No activity - idle for $MINUTES_IDLE/$IDLE_MINUTES minutes (shutdown in $REMAINING min)"

    if [ $IDLE_COUNT -ge $REQUIRED_IDLE_CHECKS ]; then
      echo ""
      echo "=========================================="
      echo "⚠️  IDLE THRESHOLD REACHED"
      echo "=========================================="
      echo "Shutdown triggered at: $(date)"
      echo "Idle time: $MINUTES_IDLE minutes"
      echo "Shutting down all vLLM models..."

      pkill -f vllm

      echo "✓ Models stopped successfully"
      echo ""
      echo "💰 Cost savings: Pod is still running but models are stopped"
      echo "📋 Action required: Stop the pod in RunPod dashboard"
      echo ""
      echo "To restart models:"
      echo "  bash /workspace/start_vllm_multi.sh"
      echo ""
      echo "=========================================="

      exit 0
    fi
  fi

  sleep $CHECK_INTERVAL
done
