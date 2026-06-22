#!/bin/bash
set -e

# Run-time harness script for the browser-use Python framework.
/setup-browser-use.sh

source /tmp/browser-use-env.sh

echo "Starting API translation proxy (litellm)..."
PYTHONPATH="/tmp${PYTHONPATH:+:$PYTHONPATH}" \
  litellm --config /tmp/litellm-config.yaml --port 4000 \
  > /data/proxy.log 2>&1 &
PROXY_PID=$!
for i in $(seq 1 30); do
  if curl -sf http://localhost:4000/health/liveliness > /dev/null 2>&1; then
    echo "API proxy ready"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "API proxy not ready after 30s — check /data/proxy.log"
    echo "proxy_failed" > /data/.stop-reason
    exit 1
  fi
  sleep 1
done

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
  if curl -sf "${CLAWBENCH_BROWSER_CDP_URL%/}/json/version" > /dev/null 2>&1; then
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

# Restrict PATH to safe read-only commands
# python3 is included because the agent itself is a Python script.
SAFE_BIN=/tmp/safe-bin
mkdir -p "$SAFE_BIN"
for cmd in ls cat find file jq cut uniq head tail tr wc grep sort sh bash; do
  [ -x "$(command -v "$cmd" 2>/dev/null)" ] && ln -sf "$(command -v "$cmd")" "$SAFE_BIN/$cmd"
done
ln -sf "$(command -v python3)" "$SAFE_BIN/python3"

# Run the browser-use agent driver. The script writes its transcript
# to /data/agent-messages.jsonl after every step. Stdout/stderr go to
# /tmp so the post-run cleanup doesn't include them in the run output.
cd "$WORKSPACE"
echo "Starting browser-use agent (model=${BU_MODEL_NAME})..."
: > /data/usage.jsonl
PATH="$SAFE_BIN" python3 /run-browser-use-agent.py \
  > /tmp/browser-use-stdout.log 2> /tmp/browser-use-stderr.log &
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

# Kill browser-use agent, LiteLLM proxy, and any Playwright stragglers
kill $AGENT_PID 2>/dev/null || true
kill $PROXY_PID 2>/dev/null || true
pkill -f "run-browser-use-agent" 2>/dev/null || true
pkill -f "browser_use"           2>/dev/null || true
pkill -f "playwright"            2>/dev/null || true
pkill -f "litellm"               2>/dev/null || true
sleep 2
python3 /usage-emitter.py --harness browser-use --input /data/agent-messages.jsonl --output /data/usage.jsonl || true

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
