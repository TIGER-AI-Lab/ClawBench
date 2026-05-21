#!/bin/bash
set -e

# Run-time harness script for the openclaw agent.
# Invoked by /entrypoint.sh (base image) after the shared infra (Xvfb,
# Chrome, extension-server, noVNC) is up and the manual/human branches
# have been ruled out. Requires INSTRUCTION, MODEL_NAME, BASE_URL,
# API_TYPE, API_KEYS/API_KEY in the environment.

# Generate a shared gateway token so gateway and agent can authenticate
OPENCLAW_GATEWAY_TOKEN="$(head -c 32 /dev/urandom | od -A n -t x1 | tr -d ' \n')"
export OPENCLAW_GATEWAY_TOKEN

# Generate OpenClaw config from env vars
/setup-openclaw.sh

# Copy /my-info/ into the OpenClaw workspace so the agent can access it via ./my-info/
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

# Start OpenClaw gateway (log to /data for post-mortem debugging)
openclaw gateway run > /data/gateway.log 2>&1 &
GATEWAY_PID=$!
sleep 3

# Check gateway is alive
if ! kill -0 $GATEWAY_PID 2>/dev/null; then
  echo "ERROR: OpenClaw gateway died on startup. Log:"
  cat /data/gateway.log
  echo "gateway_failed" > /data/.stop-reason
  exit 1
fi
echo "OpenClaw gateway running (pid=$GATEWAY_PID)"

# Run the agent from workspace directory (where my-info/ lives)
echo "Starting OpenClaw agent from $WORKSPACE..."
TIMEOUT_MS=$(( ${TIME_LIMIT_S:-1800} * 1000 ))
AGENT_CMD=(openclaw agent --session-id clawbench --message "$INSTRUCTION" --thinking "${THINKING_LEVEL:-medium}" --timeout "$TIMEOUT_MS" --local)
echo "Agent command: ${AGENT_CMD[*]}"
if [ -n "$TEMPERATURE" ]; then
  AGENT_CMD+=(--temperature "$TEMPERATURE")
fi
if [ -n "$MAX_TOKENS" ]; then
  AGENT_CMD+=(--max-tokens "$MAX_TOKENS")
fi
cd "$WORKSPACE"
"${AGENT_CMD[@]}" > /data/agent.log 2>&1 &
AGENT_PID=$!

# Watchdog: wait for agent activity, then detect idle (no new actions for 300s)
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

# Kill all openclaw processes
kill $AGENT_PID 2>/dev/null || true
kill $GATEWAY_PID 2>/dev/null || true
pkill -f "openclaw" 2>/dev/null || true
sleep 2

# Copy OpenClaw session transcript to /data
cp /root/.openclaw/agents/main/sessions/clawbench.jsonl /data/agent-messages.jsonl 2>/dev/null || true

# Finalize bookkeeping (eval promotion, etc.) — recording keeps running
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
