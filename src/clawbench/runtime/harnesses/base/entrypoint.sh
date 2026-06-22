#!/bin/bash
set -e

# Ensure /data exists for recording output and diagnostic logs
mkdir -p /data

export CLAWBENCH_BROWSER_CDP_URL="${CLAWBENCH_BROWSER_CDP_URL:-http://127.0.0.1:9222}"

# Start virtual display
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99
sleep 1

# Start the server
cd /app/src/runtime-server
uv run --no-sync uvicorn server:app --host 0.0.0.0 --port 7878 &
sleep 1

# Start Chrome with extension (dummy profile to reduce bot detection)
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

# Browser binary: default chromium (every harness but claude-code-chrome-extension).
# Harness layers can override via `ENV BROWSER_BINARY=google-chrome-stable` when
# they need a Chrome-family browser that supports features Chromium lacks (e.g.
# the Claude in Chrome extension's native-messaging handshake).
BROWSER="${BROWSER_BINARY:-chromium}"

# Extensions: always load the ClawBench recorder. A harness layer can append
# additional unpacked extensions (comma-separated paths) via EXTRA_LOAD_EXTENSIONS
# for extension-based harnesses like the Claude in Chrome extension.
LOAD_EXTS="/app/src/chrome-extension${EXTRA_LOAD_EXTENSIONS:+,$EXTRA_LOAD_EXTENSIONS}"

"$BROWSER" \
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
  --disable-features=PasswordLeakDetection,PasswordManager,DisableLoadExtensionCommandLineSwitch \
  --user-data-dir=/tmp/chrome-profile \
  --remote-debugging-port=9222 \
  --remote-debugging-address=127.0.0.1 \
  --remote-allow-origins=* \
  --load-extension="$LOAD_EXTS" \
  --disable-extensions-except="$LOAD_EXTS" \
  about:blank &

# Forward CDP port to all interfaces
sleep 2
socat TCP-LISTEN:9223,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:9222 &

# Always start noVNC so users can watch the browser in any mode.
# In human mode x11vnc also fires disconnect hooks for the watchdog.
echo "Starting noVNC..."
VNC_GONE_HOOK=""
VNC_ACCEPT_HOOK=""
if [ "$HUMAN_MODE" = "1" ]; then
  VNC_GONE_HOOK="-gone touch /data/.vnc-disconnected"
  VNC_ACCEPT_HOOK="-afteraccept rm -f /data/.vnc-disconnected"
fi
x11vnc -display :99 -nopw -shared -forever -rfbport 5900 -xkb \
  $VNC_GONE_HOOK $VNC_ACCEPT_HOOK &
sleep 1

/opt/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 6080 &
sleep 1
echo "============================================"
echo "noVNC ready: http://localhost:6080/vnc.html"
echo "============================================"

# Human mode: wait for VNC disconnect or eval match
if [ "$HUMAN_MODE" = "1" ]; then
  echo "Human mode active."
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

# DEBUG mode: If no INSTRUCTION provided, skip the harness and keep container alive for external testing
if [ -z "$INSTRUCTION" ]; then
  echo "No INSTRUCTION set, running in manual mode (no agent harness)."
  wait -n
  exit 0
fi

# Delegate agent mode to the harness-specific runner, installed by the per-harness Dockerfile layer
if [ ! -x /run-harness.sh ]; then
  echo "ERROR: /run-harness.sh missing — image was built without a harness layer"
  echo "missing_harness" > /data/.stop-reason
  exit 1
fi
exec /run-harness.sh
