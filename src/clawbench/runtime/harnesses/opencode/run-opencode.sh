#!/bin/bash
set -e

# Run-time harness script for the opencode agent.
/setup-opencode.sh

# Map API_TYPE to the provider id that setup-opencode.sh registered.
case "$API_TYPE" in
  anthropic-messages)   PROVIDER_ID="anthropic" ;;
  openai-responses)     PROVIDER_ID="openai" ;;
  openai-completions)   PROVIDER_ID="openai-compat" ;;
  google-generative-ai) PROVIDER_ID="google" ;;
  *) echo "ERROR: unsupported API_TYPE '$API_TYPE'"; exit 1 ;;
esac

# Copy /my-info/ into the workspace so the agent can access it via ./my-info/
WORKSPACE=/root/workspace
mkdir -p "$WORKSPACE"
if [ -d /my-info ]; then
  cp -r /my-info "$WORKSPACE/my-info"
  echo "Copied /my-info to $WORKSPACE/my-info"
fi

# Wait for Chrome CDP to be ready
echo "Waiting for Chrome CDP..."
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:9222/json/version > /dev/null 2>&1; then
    echo "Chrome CDP ready"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "Chrome CDP not ready after 30s, aborting"
    echo "chrome_cdp_timeout" > /data/.stop-reason
    exit 1
  fi
  sleep 1
done

# Skip permission prompts
export OPENCODE_YOLO=true

# Run the agent from workspace dir; stream its --format json events
# directly to /data/agent-messages.jsonl.
cd "$WORKSPACE"
echo "Starting opencode agent (model=${PROVIDER_ID}/${MODEL_NAME})..."
# `--thinking` is the gate that publishes `reasoning` parts to the JSONL
# stream; without it opencode silently drops them even when the model emits
# reasoning tokens. Skip when THINKING_LEVEL is explicitly off.
OPENCODE_ARGS=(run --model "${PROVIDER_ID}/${MODEL_NAME}" --format json)
case "${THINKING_LEVEL:-medium}" in
  ""|off) ;;
  *) OPENCODE_ARGS+=(--thinking) ;;
esac
OPENCODE_ARGS+=("$INSTRUCTION")
opencode "${OPENCODE_ARGS[@]}" \
  > /data/agent-messages.jsonl 2> /data/agent.log &
AGENT_PID=$!
sleep 3

# Watchdog: detect agent no action for 300s
IDLE_THRESHOLD=300
MAX_WAIT=${TIME_LIMIT_S:-1800}
ELAPSED=0
LAST_SIZE=0
IDLE=0
STOP_REASON=""

while kill -0 $AGENT_PID 2>/dev/null && [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
  sleep 5
  ELAPSED=$((ELAPSED + 5))

  # Check if server requested stop (eval interceptor matched)
  if [ -f /data/.stop-requested ]; then
    echo "Stop requested by server (eval matched), killing agent."
    STOP_REASON="eval_matched"
    break
  fi

  CURRENT_SIZE=$(wc -c < /data/actions.jsonl 2>/dev/null || echo 0)

  if [ "$CURRENT_SIZE" -gt 0 ] && [ "$CURRENT_SIZE" -eq "$LAST_SIZE" ]; then
    IDLE=$((IDLE + 5))
    if [ "$IDLE" -ge "$IDLE_THRESHOLD" ]; then
      echo "Agent idle for ${IDLE_THRESHOLD}s, assuming done."
      STOP_REASON="agent_idle"
      break
    fi
  else
    IDLE=0
  fi
  LAST_SIZE=$CURRENT_SIZE
done

# Determine stop reason if not set (loop exited without breaking)
if [ -z "$STOP_REASON" ]; then
  if ! kill -0 $AGENT_PID 2>/dev/null; then
    STOP_REASON="agent_exited"
  else
    echo "Time limit (${MAX_WAIT}s) exceeded, killing agent."
    STOP_REASON="time_limit_exceeded"
  fi
fi

echo "$STOP_REASON" > /data/.stop-reason

# Kill opencode and any MCP child processes
kill $AGENT_PID 2>/dev/null || true
pkill -f "opencode" 2>/dev/null || true
pkill -f "@playwright/mcp" 2>/dev/null || true
sleep 2

curl -sf -X POST http://localhost:7878/api/stop || true

# Clean up internal marker (created by /api/stop)
rm -f /data/.stop-requested

# Grace period: keep recording for 15s after agent is killed to capture end result
echo "Agent finished, recording grace period (15s)..."
sleep 15

# Stop recording
echo "Stopping recording..."
curl -sf -X POST http://localhost:7878/api/stop-recording || true
sleep 2
rm -f /data/*.log
echo "Done."
