#!/bin/bash
set -e

# Run-time harness script for the OpenAI Codex CLI agent.
/setup-codex.sh

# Source the env vars written by setup (CODEX_API_KEY).
source /tmp/codex-env.sh

# Start LiteLLM translation proxy.
echo "Starting API translation proxy (litellm)..."
litellm --config /tmp/litellm-config.yaml --port 4000 \
  > /tmp/codex-litellm.log 2>&1 &
PROXY_PID=$!
for i in $(seq 1 30); do
  if curl -sf http://localhost:4000/health/liveliness > /dev/null 2>&1; then
    echo "API proxy ready"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "API proxy not ready after 30s — check /tmp/codex-litellm.log"
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
SAFE_BIN=/tmp/safe-bin
mkdir -p "$SAFE_BIN"
for cmd in ls cat find file jq cut uniq head tail tr wc grep sort sh bash; do
  [ -x "$(command -v "$cmd" 2>/dev/null)" ] && ln -sf "$(command -v "$cmd")" "$SAFE_BIN/$cmd"
done
ln -sf "$(command -v codex)" "$SAFE_BIN/codex"
ln -sf "$(command -v node)"  "$SAFE_BIN/node"
ln -sf "$(command -v npx)"   "$SAFE_BIN/npx"
ln -sf "$(command -v npm)"   "$SAFE_BIN/npm"

# Build the codex command.
#   exec                                   non-interactive subcommand.
#   --json                                 stream one JSON event per line to stdout.
#   --skip-git-repo-check                  workspace isn't a git repo; codex would
#                                          otherwise refuse to run.
#   --dangerously-bypass-approvals-and-sandbox
cd "$WORKSPACE"
echo "Starting Codex CLI agent (model=${MODEL_NAME})..."
CODEX_ARGS=(exec
  --json
  --skip-git-repo-check
  --dangerously-bypass-approvals-and-sandbox
  -- "$INSTRUCTION")
: > /data/usage.jsonl
PATH="$SAFE_BIN" codex "${CODEX_ARGS[@]}" \
  > /tmp/codex-stdout.jsonl 2> /tmp/codex-agent.log &
AGENT_PID=$!
python3 /usage-emitter.py --harness codex --input /tmp/codex-stdout.jsonl --output /data/usage.jsonl --watch &
USAGE_PID=$!
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

# Kill Codex, MCP, and LiteLLM proxy processes
kill $AGENT_PID 2>/dev/null || true
kill $USAGE_PID 2>/dev/null || true
kill $PROXY_PID 2>/dev/null || true
pkill -f "@openai/codex"      2>/dev/null || true
pkill -f "@playwright/mcp"    2>/dev/null || true
pkill -f "litellm"            2>/dev/null || true
sleep 2

# Promote the session rollout to /data/agent-messages.jsonl.
LATEST_ROLLOUT=$(find /root/.codex/sessions -name "rollout-*.jsonl" -type f \
  -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
if [ -n "$LATEST_ROLLOUT" ]; then
  cp "$LATEST_ROLLOUT" /data/agent-messages.jsonl
  echo "Promoted session rollout to /data/agent-messages.jsonl"
  python3 /usage-emitter.py --harness codex --input /data/agent-messages.jsonl --output /data/usage.jsonl || true
elif [ -s /tmp/codex-stdout.jsonl ]; then
  cp /tmp/codex-stdout.jsonl /data/agent-messages.jsonl
  echo "WARN: no rollout found; fell back to stdout capture"
  python3 /usage-emitter.py --harness codex --input /data/agent-messages.jsonl --output /data/usage.jsonl || true
fi

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
