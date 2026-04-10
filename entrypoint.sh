#!/bin/bash
set -e

# Ensure /data exists for recording output and diagnostic logs
mkdir -p /data

# Start virtual display
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99
sleep 1

# Start the server
cd /app/extension-server
uv run uvicorn server:app --host 0.0.0.0 --port 7878 &
sleep 1

# Start Chrome with extension (realistic profile to reduce bot detection)
mkdir -p /tmp/chrome-profile/Default

cat > /tmp/chrome-profile/Default/Preferences <<'PREFS'
{
  "credentials_enable_service": false,
  "profile": {
    "password_manager_enabled": false,
    "password_manager_leak_detection": false,
    "name": "Default",
    "created_by_version": "131.0.6778.139",
    "content_settings": {
      "exceptions": {}
    }
  },
  "browser": {
    "has_seen_welcome_page": true,
    "check_default_browser": false,
    "window_placement": {
      "bottom": 1080,
      "left": 0,
      "maximized": false,
      "right": 1920,
      "top": 0,
      "work_area_bottom": 1080,
      "work_area_left": 0,
      "work_area_right": 1920,
      "work_area_top": 0
    }
  },
  "dns_prefetching": {
    "enabled": true
  },
  "safebrowsing": {
    "enabled": true
  },
  "search": {
    "suggest_enabled": true
  },
  "translate": {
    "enabled": false
  },
  "intl": {
    "accept_languages": "en-US,en"
  },
  "distribution": {
    "import_bookmarks": false,
    "skip_first_run_ui": true
  }
}
PREFS

cat > /tmp/chrome-profile/Default/Bookmarks <<'BOOKMARKS'
{
  "checksum": "b5f7e1a2c3d4e5f6a7b8c9d0e1f2a3b4",
  "roots": {
    "bookmark_bar": {
      "children": [
        {
          "date_added": "13350000000000000",
          "date_last_used": "0",
          "guid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "name": "Google",
          "type": "url",
          "url": "https://www.google.com/"
        },
        {
          "date_added": "13350000000000000",
          "date_last_used": "0",
          "guid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
          "name": "YouTube",
          "type": "url",
          "url": "https://www.youtube.com/"
        },
        {
          "date_added": "13350000000000000",
          "date_last_used": "0",
          "guid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
          "name": "Wikipedia",
          "type": "url",
          "url": "https://en.wikipedia.org/"
        }
      ],
      "date_added": "13350000000000000",
      "date_last_used": "0",
      "date_modified": "13350000000000000",
      "guid": "00000000-0000-4000-a000-000000000001",
      "name": "Bookmarks bar",
      "type": "folder"
    },
    "other": {
      "children": [],
      "date_added": "13350000000000000",
      "date_last_used": "0",
      "date_modified": "0",
      "guid": "00000000-0000-4000-a000-000000000002",
      "name": "Other bookmarks",
      "type": "folder"
    },
    "synced": {
      "children": [],
      "date_added": "13350000000000000",
      "date_last_used": "0",
      "date_modified": "0",
      "guid": "00000000-0000-4000-a000-000000000003",
      "name": "Mobile bookmarks",
      "type": "folder"
    }
  },
  "version": 1
}
BOOKMARKS

cat > /tmp/chrome-profile/'Local State' <<'LOCALSTATE'
{
  "browser": {
    "enabled_labs_experiments": []
  },
  "profile": {
    "info_cache": {
      "Default": {
        "active_time": 1710000000,
        "is_consented_primary_account": false,
        "name": "Person 1"
      }
    }
  },
  "user_experience_metrics": {
    "reporting_enabled": false
  }
}
LOCALSTATE

chromium \
  --window-size=1920,1080 \
  --window-position=0,0 \
  --no-first-run \
  --disable-default-apps \
  --no-sandbox \
  --disable-infobars \
  --disable-dev-shm-usage \
  --disable-blink-features=AutomationControlled \
  --use-gl=angle --use-angle=swiftshader \
  --enable-unsafe-swiftshader \
  --enable-webgl \
  --password-store=basic \
  --use-mock-keychain \
  --disable-sync \
  --disable-features=PasswordLeakDetection,PasswordManager \
  --user-data-dir=/tmp/chrome-profile \
  --remote-debugging-port=9222 \
  --remote-debugging-address=127.0.0.1 \
  --remote-allow-origins=* \
  --load-extension=/app/chrome-extension \
  --disable-extensions-except=/app/chrome-extension \
  about:blank &

# Forward CDP port to all interfaces
sleep 2
socat TCP-LISTEN:9223,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:9222 &

# Human mode: expose display via noVNC, wait for VNC disconnect or eval match
if [ "$HUMAN_MODE" = "1" ]; then
  echo "Starting human mode with noVNC..."

  # Start x11vnc with disconnect/reconnect hooks
  x11vnc -display :99 -nopw -shared -forever -rfbport 5900 -xkb \
    -gone "touch /data/.vnc-disconnected" \
    -afteraccept "rm -f /data/.vnc-disconnected" &
  sleep 1

  # Start noVNC websocket proxy (browser-based VNC client on port 6080)
  /opt/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 6080 &
  sleep 1

  echo "============================================"
  echo "noVNC ready: http://localhost:6080/vnc.html"
  echo "============================================"
  if [ -n "$INSTRUCTION" ]; then
    echo ""
    echo "TASK: $INSTRUCTION"
    echo ""
  fi

  # Human watchdog: no idle detection (humans pause to think)
  MAX_WAIT=${TIME_LIMIT_S:-1800}
  ELAPSED=0
  DISCONNECT_WAIT=0
  STOP_REASON=""

  while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))

    # Check if eval interceptor matched
    if [ -f /data/.stop-requested ]; then
      echo "Stop requested by server (eval matched)."
      STOP_REASON="eval_matched"
      break
    fi

    # Check if VNC client disconnected (with 15s grace period for reconnect)
    if [ -f /data/.vnc-disconnected ]; then
      DISCONNECT_WAIT=$((DISCONNECT_WAIT + 5))
      if [ "$DISCONNECT_WAIT" -ge 15 ]; then
        echo "VNC client disconnected for ${DISCONNECT_WAIT}s, assuming done."
        STOP_REASON="vnc_disconnected"
        break
      fi
    else
      DISCONNECT_WAIT=0
    fi
  done

  if [ -z "$STOP_REASON" ]; then
    echo "Time limit (${MAX_WAIT}s) exceeded."
    STOP_REASON="time_limit_exceeded"
  fi

  echo "$STOP_REASON" > /data/.stop-reason

  # Finalize bookkeeping (eval promotion, etc.) — recording keeps running
  curl -sf -X POST http://localhost:7878/api/stop || true
  rm -f /data/.stop-requested /data/.vnc-disconnected

  # Grace period: keep recording for 15s to capture end state
  echo "Human finished, recording grace period (15s)..."
  sleep 15

  # Stop recording
  echo "Stopping recording..."
  curl -sf -X POST http://localhost:7878/api/stop-recording || true
  sleep 2
  echo "Done."
  exit 0
fi

# If no INSTRUCTION provided, skip OpenClaw and keep container alive for external use
if [ -z "$INSTRUCTION" ]; then
  echo "No INSTRUCTION set, running in manual mode (no OpenClaw agent)."
  wait -n
  exit 0
fi

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
echo "Done."
