#!/bin/bash
set -e

# Run-time harness script for the Harbor framework's Terminus 2 agent.
/setup-harbor.sh

# Copy /my-info/ into the workspace so the agent can access it via ./my-info/
WORKSPACE=/root/workspace
mkdir -p "$WORKSPACE"
if [ -d /my-info ]; then
  cp -r /my-info "$WORKSPACE/my-info"
  echo "Copied /my-info to $WORKSPACE/my-info"
fi

# Wait for Chrome CDP to be ready. Terminus drives this same browser through the
# agent-browser CLI, preserving ClawBench's recorder extension and interceptor.
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

cd "$WORKSPACE"
echo "Starting Harbor agent (Terminus 2, model=${MODEL_NAME})..."
# Harbor lives in its own Python 3.12 venv (base image is 3.11); fall back to
# python3 only if the ENV var is somehow unset.
"${HARBOR_PYTHON:-python3}" /harbor_driver.py > /tmp/harbor-stdout.log 2> /tmp/harbor-stderr.log &
AGENT_PID=$!
sleep 3

if ! kill -0 $AGENT_PID 2>/dev/null; then
  echo "Harbor process died on startup; see /data/agent-stderr.log"
  echo "harbor_failed" > /data/.stop-reason
fi

# Watchdog: detect agent no action for 300s (same contract as pi/hermes).
IDLE_THRESHOLD=300
MAX_WAIT=${TIME_LIMIT_S:-1800}
ELAPSED=0
LAST_SIZE=0
IDLE=0
STOP_REASON=""

while kill -0 $AGENT_PID 2>/dev/null && [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
  sleep 5
  ELAPSED=$((ELAPSED + 5))

  # Check if server requested stop (eval interceptor matched).
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

# Determine stop reason if not set (loop exited without breaking).
if [ -z "$STOP_REASON" ]; then
  if [ -f /data/.stop-reason ]; then
    STOP_REASON=$(cat /data/.stop-reason)
  elif ! kill -0 $AGENT_PID 2>/dev/null; then
    STOP_REASON="agent_exited"
  else
    echo "Time limit (${MAX_WAIT}s) exceeded, killing agent."
    STOP_REASON="time_limit_exceeded"
  fi
fi

echo "$STOP_REASON" > /data/.stop-reason

# Stop the agent and any browser helper it spawned.
kill -INT $AGENT_PID 2>/dev/null || true
sleep 2
kill $AGENT_PID 2>/dev/null || true
pkill -f "agent-browser" 2>/dev/null || true
pkill -f "harbor_driver.py" 2>/dev/null || true
sleep 2

# Promote Terminus' trajectory.json into ClawBench's /data/agent-messages.jsonl,
# one JSONL line per step (plus a meta line), like the hermes harness does.
promote_harbor_transcript() {
  local traj="/logs/agent/trajectory.json"
  if [ -s "$traj" ]; then
    python3 - "$traj" /data/agent-messages.jsonl <<'PYEOF' && return 0
import json
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
data = json.loads(src.read_text(encoding="utf-8", errors="replace"))
steps = data.get("steps") or []
meta = {k: v for k, v in data.items() if k != "steps"}
with dst.open("w", encoding="utf-8") as out:
    out.write(json.dumps({"type": "session_meta", **meta},
                         ensure_ascii=False, separators=(",", ":")) + "\n")
    for index, step in enumerate(steps):
        row = {"type": "step", "step_index": index, **step}
        out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
PYEOF
  fi
  return 1
}

if ! promote_harbor_transcript; then
  # Fallback: capture the agent's stdout/stderr so failures are diagnosable.
  if [ -s /tmp/harbor-stdout.log ] || [ -s /tmp/harbor-stderr.log ]; then
    python3 - > /data/agent-messages.jsonl <<'PYEOF'
import json
from pathlib import Path

for name, stream in (("/tmp/harbor-stdout.log", "stdout"), ("/tmp/harbor-stderr.log", "stderr")):
    p = Path(name)
    if p.exists() and p.stat().st_size:
        print(json.dumps({"type": "harbor_log", "stream": stream,
                          "content": p.read_text(errors="replace")}, ensure_ascii=False))
PYEOF
    echo "WARN: no Harbor trajectory found; captured stdout/stderr logs instead"
  else
    : > /data/agent-messages.jsonl
    echo "WARN: no Harbor trajectory or logs found; wrote empty /data/agent-messages.jsonl"
  fi
fi

cp /tmp/harbor-stdout.log /data/agent-stdout.log 2>/dev/null || true
cp /tmp/harbor-stderr.log /data/agent-stderr.log 2>/dev/null || true

curl -sf -X POST http://localhost:7878/api/stop || true

# Clean up internal marker (created by /api/stop).
rm -f /data/.stop-requested

# Grace period: keep recording for 15s after agent is killed to capture end result.
echo "Agent finished, recording grace period (15s)..."
sleep 15

# Stop recording.
echo "Stopping recording..."
curl -sf -X POST http://localhost:7878/api/stop-recording || true
sleep 2
rm -f /data/*.log
echo "Done."
