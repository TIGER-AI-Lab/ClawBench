#!/bin/bash
set -e

# Run-time harness script for the Claude Code agent.
/setup-claude-code.sh

# Source the env vars written by setup (ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL).
source /tmp/claude-code-env.sh

# Start LiteLLM translation proxy.
echo "Starting API translation proxy (litellm)..."
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

# Restrict PATH to safe read-only commands — mirrors the openclaw/opencode
# allowlist so the agent cannot bypass the browser with curl, python, etc.
# The agent binary and node/npx (needed for MCP) are also included.
SAFE_BIN=/tmp/safe-bin
mkdir -p "$SAFE_BIN"
for cmd in ls cat find file jq cut uniq head tail tr wc grep sort sh bash; do
  [ -x "$(command -v "$cmd" 2>/dev/null)" ] && ln -sf "$(command -v "$cmd")" "$SAFE_BIN/$cmd"
done
ln -sf "$(command -v claude)" "$SAFE_BIN/claude"
ln -sf "$(command -v node)"   "$SAFE_BIN/node"
ln -sf "$(command -v npx)"    "$SAFE_BIN/npx"
ln -sf "$(command -v npm)"    "$SAFE_BIN/npm"

# Build the claude command.
# -p (print mode): non-interactive, runs the prompt to completion.
# --output-format stream-json: streams one JSON object per line to stdout.
# --dangerously-skip-permissions: skip permission prompts (container is the sandbox).
# IS_SANDBOX=1 bypasses the root-user check for --dangerously-skip-permissions.
export IS_SANDBOX=1
cd "$WORKSPACE"
echo "Starting Claude Code agent (model=${MODEL_NAME})..."
CLAUDE_ARGS=(-p --verbose --output-format stream-json --model "$MODEL_NAME" --dangerously-skip-permissions)
# --thinking requires a mode: enabled | adaptive | disabled.
case "${THINKING_LEVEL:-off}" in
  ""|off)  ;;
  *)       CLAUDE_ARGS+=(--thinking enabled) ;;
esac
# --mcp-config is variadic; use -- to stop it consuming the prompt.
CLAUDE_ARGS+=(--mcp-config /tmp/claude-mcp.json -- "$INSTRUCTION")
PATH="$SAFE_BIN" claude "${CLAUDE_ARGS[@]}" \
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

# Kill Claude Code, MCP, and proxy processes
kill $AGENT_PID 2>/dev/null || true
kill $PROXY_PID 2>/dev/null || true
pkill -f "@anthropic-ai/claude-code" 2>/dev/null || true
pkill -f "@playwright/mcp" 2>/dev/null || true
pkill -f "litellm" 2>/dev/null || true
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
