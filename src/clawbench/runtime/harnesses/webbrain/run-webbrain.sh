#!/bin/bash
set -e

/setup-webbrain.sh
mkdir -p /data
: > /data/agent-messages.jsonl
: > /data/usage.jsonl

echo "Waiting for Chrome CDP..."
for i in $(seq 1 30); do
  if curl -sf "${CLAWBENCH_BROWSER_CDP_URL%/}/json/version" > /dev/null 2>&1; then
    echo "Chrome CDP ready"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "Chrome CDP not ready after 30s"
    echo "chrome_cdp_timeout" > /data/.stop-reason
    exit 1
  fi
  sleep 1
done

echo "Starting WebBrain extension agent (model=${MODEL_NAME})..."
/app/src/runtime-server/.venv/bin/python /run-webbrain-agent.py \
  > /tmp/webbrain-stdout.log 2> /tmp/webbrain-stderr.log &
AGENT_PID=$!

IDLE_THRESHOLD=300
MAX_WAIT=${TIME_LIMIT_S:-1800}
ELAPSED=0
LAST_SIZE=0
IDLE=0
STOP_REASON=""

while kill -0 "$AGENT_PID" 2>/dev/null && [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
  sleep 5
  ELAPSED=$((ELAPSED + 5))

  if [ -f /data/.stop-requested ]; then
    if ! STOP_REASON=$(/app/src/runtime-server/.venv/bin/python \
      /run-webbrain-agent.py --classify-stop-request); then
      STOP_REASON="stop_requested"
    fi
    echo "Stop requested by server (${STOP_REASON}), stopping WebBrain."
    break
  fi

  CURRENT_SIZE=$(wc -c < /data/actions.jsonl 2>/dev/null || echo 0)
  if [ "$CURRENT_SIZE" -gt 0 ] && [ "$CURRENT_SIZE" -eq "$LAST_SIZE" ]; then
    IDLE=$((IDLE + 5))
    if [ "$IDLE" -ge "$IDLE_THRESHOLD" ]; then
      echo "WebBrain idle for ${IDLE_THRESHOLD}s, assuming done."
      STOP_REASON="agent_idle"
      break
    fi
  else
    IDLE=0
  fi
  LAST_SIZE=$CURRENT_SIZE
done

AGENT_STATUS=0
if [ -z "$STOP_REASON" ]; then
  if kill -0 "$AGENT_PID" 2>/dev/null; then
    echo "Time limit (${MAX_WAIT}s) exceeded, stopping WebBrain."
    STOP_REASON="time_limit_exceeded"
  else
    wait "$AGENT_PID" || AGENT_STATUS=$?
    if [ "$AGENT_STATUS" -eq 0 ]; then
      STOP_REASON="agent_exited"
    else
      STOP_REASON="agent_error"
      echo "WebBrain driver exited with status ${AGENT_STATUS}; see captured agent messages."
    fi
  fi
fi

if kill -0 "$AGENT_PID" 2>/dev/null; then
  kill "$AGENT_PID" 2>/dev/null || true
  wait "$AGENT_PID" 2>/dev/null || true
fi

echo "$STOP_REASON" > /data/.stop-reason
python3 /usage-emitter.py
curl -sf -X POST http://localhost:7878/api/stop || true
rm -f /data/.stop-requested

echo "WebBrain finished, recording grace period (15s)..."
sleep 15
curl -sf -X POST http://localhost:7878/api/stop-recording || true
sleep 2
rm -f /data/*.log
echo "Done."
