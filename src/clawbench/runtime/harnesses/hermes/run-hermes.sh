#!/bin/bash
set -e

# Run-time harness script for Hermes Agent.
/setup-hermes.sh

# Source Hermes env vars written by setup.
source /tmp/hermes-env.sh

# Copy /my-info/ into the workspace so the agent can access it via ./my-info/
WORKSPACE=/root/workspace
mkdir -p "$WORKSPACE"
if [ -d /my-info ]; then
  cp -r /my-info "$WORKSPACE/my-info"
  echo "Copied /my-info to $WORKSPACE/my-info"
fi

# Hermes' file tool redacts/truncates secret-looking values in file previews.
# Give this harness the exact disposable webmail credentials in-band so it
# does not type a shortened password such as "abc...xyz" into the login form.
HERMES_INSTRUCTION="${INSTRUCTION}

HERMES COMPLETION NOTE:
After you click Send or otherwise submit the email, immediately provide a brief final response and stop. Do not continue browsing, signing up for other email providers, or checking unrelated account flows."
if [ -f "$WORKSPACE/my-info/email_credentials.json" ]; then
  HERMES_CREDENTIAL_NOTE=$(python3 - "$WORKSPACE/my-info/email_credentials.json" <<'PYEOF'
import json
import sys
from pathlib import Path

creds = json.loads(Path(sys.argv[1]).read_text())
email = creds.get("email", "")
password = creds.get("password", "")
login_url = creds.get("login_url", "https://purelymail.com/user/login")
provider = creds.get("provider", "PurelyMail")
if email and password:
    print(
        "\n\nHERMES CREDENTIAL NOTE:\n"
        f"The exact {provider} webmail login credentials are:\n"
        f"- login_url: {login_url}\n"
        f"- email: {email}\n"
        f"- password: {password}\n"
        "Use this exact password when logging in. Do not rely on Hermes read_file output "
        "for email_credentials.json if it shows an abbreviated or redacted password."
    )
PYEOF
)
  HERMES_INSTRUCTION="${HERMES_INSTRUCTION}${HERMES_CREDENTIAL_NOTE}"
fi

# Wait for Chrome CDP to be ready. Hermes browser tools attach to this same
# browser, preserving ClawBench's recorder extension and request interceptor.
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

promote_hermes_transcript() {
  local session_id=""
  local latest_session=""
  local raw_export="/tmp/hermes-session-export.jsonl"
  local tmp_export="/tmp/hermes-agent-messages.jsonl"
  local live_export="/tmp/hermes-live-agent-messages.jsonl"

  expand_hermes_sessions() {
    local input_path="$1"
    local output_path="$2"
    python3 - "$input_path" "$output_path" <<'PYEOF'
import json
import sys
from pathlib import Path

input_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])

with input_path.open(encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as dst:
    for line_no, line in enumerate(src, 1):
        if not line.strip():
            continue
        session = json.loads(line)
        messages = session.get("messages") or []
        meta = {k: v for k, v in session.items() if k != "messages"}
        session_id = meta.get("id") or meta.get("session_id")
        dst.write(json.dumps({
            "type": "session_meta",
            **meta,
        }, ensure_ascii=False, separators=(",", ":")) + "\n")
        for index, message in enumerate(messages):
            row = {
                "type": "message",
                "session_id": session_id,
                "message_index": index,
                **message,
            }
            dst.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
PYEOF
  }

  use_live_capture_if_present() {
    if [ -s "$live_export" ]; then
      cp "$live_export" /data/agent-messages.jsonl
      echo "Promoted live Hermes capture to /data/agent-messages.jsonl"
      return 0
    fi
    return 1
  }

  has_message_rows() {
    local path="$1"
    python3 - "$path" <<'PYEOF'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
for line in path.read_text(errors="replace").splitlines():
    if not line.strip():
        continue
    row = json.loads(line)
    if row.get("type") != "session_meta":
        raise SystemExit(0)
raise SystemExit(1)
PYEOF
  }

  session_id=$(grep -Eo 'session_id:[[:space:]]*[^[:space:]]+' /tmp/hermes-stderr.log 2>/dev/null | awk '{print $2}' | tail -1 || true)

  if [ -z "$session_id" ]; then
    latest_session=$(find /root/.hermes/sessions -name "session_*.json" -type f \
      -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
    if [ -n "$latest_session" ]; then
      session_id=$(python3 - "$latest_session" <<'PYEOF' || true
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text())
    print(data.get("session_id") or data.get("id") or path.stem.replace("session_", ""))
except Exception:
    print(path.stem.replace("session_", ""))
PYEOF
)
    fi
  fi

  if [ -n "$session_id" ]; then
    if hermes sessions export - --session-id "$session_id" > "$raw_export" 2>/tmp/hermes-export.log && [ -s "$raw_export" ]; then
      expand_hermes_sessions "$raw_export" "$tmp_export"
      if has_message_rows "$tmp_export"; then
        mv "$tmp_export" /data/agent-messages.jsonl
        echo "Exported Hermes session $session_id to multiline /data/agent-messages.jsonl"
        return
      fi
      echo "WARN: Hermes session export had no messages; falling back to live capture"
      use_live_capture_if_present && return
    fi
    echo "WARN: Hermes session export failed for session_id=$session_id; falling back to session JSON if available"
  fi

  if [ -z "$latest_session" ]; then
    latest_session=$(find /root/.hermes/sessions -name "session_*.json" -type f \
      -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
  fi

  if [ -n "$latest_session" ]; then
    python3 - "$latest_session" > "$raw_export" <<'PYEOF'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text())
print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
PYEOF
    expand_hermes_sessions "$raw_export" "$tmp_export"
    if has_message_rows "$tmp_export"; then
      mv "$tmp_export" /data/agent-messages.jsonl
      echo "Promoted Hermes session JSON to multiline /data/agent-messages.jsonl"
      return
    fi
    echo "WARN: Hermes session JSON had no messages; falling back to live capture"
    use_live_capture_if_present && return
  fi

  use_live_capture_if_present && return

  if [ -s /tmp/hermes-stdout.log ] || [ -s /tmp/hermes-stderr.log ]; then
    python3 - > /data/agent-messages.jsonl <<'PYEOF'
import json
from pathlib import Path

for name, role in (("/tmp/hermes-stdout.log", "stdout"), ("/tmp/hermes-stderr.log", "stderr")):
    path = Path(name)
    if path.exists() and path.stat().st_size:
        print(json.dumps({"type": "hermes_log", "stream": role, "content": path.read_text(errors="replace")}, ensure_ascii=False))
PYEOF
    echo "WARN: no Hermes session found; captured stdout/stderr logs instead"
    return
  fi

  : > /data/agent-messages.jsonl
  echo "WARN: no Hermes session or logs found; wrote empty /data/agent-messages.jsonl"
}

terminate_hermes() {
  local pid="$1"
  if kill -0 "$pid" 2>/dev/null; then
    # Prefer SIGINT so Hermes can flush its session transcript before exit.
    kill -INT "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
    for _ in $(seq 1 10); do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
  fi
}

cd "$WORKSPACE"
echo "Starting Hermes agent (model=${HERMES_MODEL_NAME}, provider=${HERMES_PROVIDER})..."
HERMES_ARGS=(chat
  --quiet
  --yolo
  --ignore-rules
  --toolsets "browser,file"
  --max-turns 90
  --model "$HERMES_MODEL_NAME"
  --provider "$HERMES_PROVIDER"
  -q "$HERMES_INSTRUCTION")
: > /data/usage.jsonl
python3 /hermes-capture.py "${HERMES_ARGS[@]}" > /tmp/hermes-stdout.log 2> /tmp/hermes-stderr.log &
AGENT_PID=$!
python3 /usage-emitter.py --harness hermes --input /tmp/hermes-live-agent-messages.jsonl --output /data/usage.jsonl --watch &
USAGE_PID=$!
sleep 3

if ! kill -0 $AGENT_PID 2>/dev/null; then
  echo "Hermes process died on startup."
  echo "hermes_failed" > /data/.stop-reason
fi

# Watchdog: detect agent no action for 300s.
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
    echo "Stop requested by server (eval matched), waiting briefly for Hermes to flush."
    STOP_REASON="eval_matched"
    for _ in $(seq 1 24); do
      if ! kill -0 $AGENT_PID 2>/dev/null; then
        break
      fi
      sleep 5
    done
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

# Terminate Hermes first so it can flush its session, then clean up the native
# browser helper process if it is still alive.
terminate_hermes "$AGENT_PID"
kill "$USAGE_PID" 2>/dev/null || true
pkill -f "agent-browser" 2>/dev/null || true
sleep 2

promote_hermes_transcript
python3 /usage-emitter.py --harness hermes --input /data/agent-messages.jsonl --output /data/usage.jsonl || true
cp /tmp/hermes-stdout.log /data/agent-stdout.log 2>/dev/null || true
cp /tmp/hermes-stderr.log /data/agent-stderr.log 2>/dev/null || true
cp /tmp/hermes-export.log /data/hermes-export.log 2>/dev/null || true

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
