#!/bin/bash
set -e

# Run-time harness script for the Pi coding agent.
/setup-pi.sh

source /tmp/pi-env.sh

# Start LiteLLM translation proxy.
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
    echo "API proxy not ready after 30s; check /data/proxy.log"
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

# Wait for Chrome CDP to be ready and expose the browser-level websocket URL
# to pi-browser-harness. The extension will attach to this browser instead of
# launching its own Chrome instance.
echo "Waiting for Chrome CDP..."
for i in $(seq 1 30); do
  if curl -sf "${CLAWBENCH_BROWSER_CDP_URL%/}/json/version" > /tmp/chrome-version.json 2>/dev/null; then
    export BU_CDP_WS
    BU_CDP_WS=$(python3 - <<'PYEOF'
import json
from pathlib import Path

data = json.loads(Path("/tmp/chrome-version.json").read_text())
ws = data.get("webSocketDebuggerUrl")
if not isinstance(ws, str) or not ws:
    raise SystemExit("missing webSocketDebuggerUrl")
print(ws)
PYEOF
)
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

# Restrict PATH to safe read-only commands and the Pi runtime. The Pi tool
# allowlist below is authoritative, but the PATH guard gives the harness the
# same posture as other CLI harnesses if a shell path is reached unexpectedly.
SAFE_BIN=/tmp/safe-bin
mkdir -p "$SAFE_BIN"
for cmd in ls cat find file head tail wc grep sort sh bash; do
  [ -x "$(command -v "$cmd" 2>/dev/null)" ] && ln -sf "$(command -v "$cmd")" "$SAFE_BIN/$cmd"
done
ln -sf "$(command -v pi)"   "$SAFE_BIN/pi"
ln -sf "$(command -v node)" "$SAFE_BIN/node"

PI_BROWSER_EXTENSION=/usr/local/lib/node_modules/pi-browser-harness
PI_TOOLS="read,grep,find,ls,browser_navigate,browser_new_tab,browser_list_tabs,browser_current_tab,browser_switch_tab,browser_page_info,browser_screenshot,browser_snapshot,browser_click,browser_type,browser_press_key,browser_scroll,browser_wait,browser_wait_for_load,browser_go_back,browser_go_forward,browser_reload,browser_handle_dialog,browser_execute_js"
PI_BROWSER_PROMPT="Complete the task using the browser_* tools attached to the existing ClawBench browser. Do not use browser_http_get, browser_run_script, bash, write, or edit; those tools are intentionally unavailable."

cd "$WORKSPACE"
echo "Starting Pi agent (model=${PI_PROVIDER}/${PI_MODEL_ID}, thinking=${PI_THINKING})..."
PI_RAW_MESSAGES=/data/agent-messages.raw.jsonl
: > /data/usage.jsonl
PATH="$SAFE_BIN" pi \
  --mode json \
  --print \
  --no-session \
  --provider "$PI_PROVIDER" \
  --model "$PI_MODEL_ID" \
  --thinking "$PI_THINKING" \
  --no-extensions \
  --extension "$PI_BROWSER_EXTENSION" \
  --no-skills \
  --no-prompt-templates \
  --no-themes \
  --no-context-files \
  --tools "$PI_TOOLS" \
  --append-system-prompt "$PI_BROWSER_PROMPT" \
  "$INSTRUCTION" \
  > "$PI_RAW_MESSAGES" 2> /data/agent.log &
AGENT_PID=$!
python3 /usage-emitter.py --harness pi --input "$PI_RAW_MESSAGES" --output /data/usage.jsonl --watch &
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

# Kill Pi and proxy processes
kill $AGENT_PID 2>/dev/null || true
kill $USAGE_PID 2>/dev/null || true
kill $PROXY_PID 2>/dev/null || true
pkill -f "@earendil-works/pi-coding-agent" 2>/dev/null || true
pkill -f "litellm" 2>/dev/null || true
sleep 2

# Filter raw Pi messages to remove message updates with all these *_delta events
if [ -f "$PI_RAW_MESSAGES" ]; then
  python3 - "$PI_RAW_MESSAGES" /data/agent-messages.jsonl <<'PYEOF' || cp "$PI_RAW_MESSAGES" /data/agent-messages.jsonl
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
with open(src, encoding="utf-8", errors="replace") as inp, open(dst, "w", encoding="utf-8") as out:
    for line in inp:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            out.write(line)
            continue
        if isinstance(event, dict) and event.get("type") == "message_update":
            continue
        out.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        out.write("\n")
PYEOF
  rm -f "$PI_RAW_MESSAGES"
else
  : > /data/agent-messages.jsonl
fi
python3 /usage-emitter.py --harness pi --input /data/agent-messages.jsonl --output /data/usage.jsonl || true

rm -f /data/agent.log /data/proxy.log

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
