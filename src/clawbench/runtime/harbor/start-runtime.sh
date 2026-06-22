#!/bin/bash
set -euo pipefail

mkdir -p /data /tmp/clawbench-run

if [ -f /tmp/clawbench-run/runtime.pid ] && kill -0 "$(cat /tmp/clawbench-run/runtime.pid)" 2>/dev/null; then
  echo "ClawBench Harbor runtime is already running."
  exit 0
fi

export DISPLAY="${DISPLAY:-:99}"
Xvfb "$DISPLAY" -screen 0 1920x1080x24 >/tmp/clawbench-run/xvfb.log 2>&1 &
echo "$!" > /tmp/clawbench-run/xvfb.pid
sleep 1

cd /app/src/runtime-server
uv run --no-sync uvicorn server:app --host 0.0.0.0 --port 7878 >/tmp/clawbench-run/runtime-server.log 2>&1 &
echo "$!" > /tmp/clawbench-run/runtime-server.pid
sleep 1

mkdir -p /tmp/chrome-profile/Default
cat > /tmp/chrome-profile/Default/Preferences <<'PREFS'
{
  "credentials_enable_service": false,
  "profile": {
    "password_manager_enabled": false,
    "password_manager_leak_detection": false,
    "name": "Default"
  },
  "browser": {
    "has_seen_welcome_page": true,
    "check_default_browser": false,
    "window_placement": {
      "bottom": 1080,
      "left": 0,
      "right": 1920,
      "top": 0
    }
  },
  "distribution": {
    "import_bookmarks": false,
    "skip_first_run_ui": true
  },
  "intl": {
    "accept_languages": "en-US,en"
  },
  "translate": {
    "enabled": false
  }
}
PREFS

cat > /tmp/chrome-profile/Default/Bookmarks <<'BOOKMARKS'
{
  "roots": {
    "bookmark_bar": {
      "children": [
        {"name": "Google", "type": "url", "url": "https://www.google.com/"},
        {"name": "YouTube", "type": "url", "url": "https://www.youtube.com/"},
        {"name": "Wikipedia", "type": "url", "url": "https://en.wikipedia.org/"}
      ],
      "name": "Bookmarks bar",
      "type": "folder"
    },
    "other": {"children": [], "name": "Other bookmarks", "type": "folder"},
    "synced": {"children": [], "name": "Mobile bookmarks", "type": "folder"}
  },
  "version": 1
}
BOOKMARKS

cat > /tmp/chrome-profile/'Local State' <<'LOCALSTATE'
{
  "browser": {
    "enabled_labs_experiments": []
  },
  "user_experience_metrics": {
    "reporting_enabled": false
  }
}
LOCALSTATE

BROWSER="${BROWSER_BINARY:-chromium}"
LOAD_EXTS="/app/src/chrome-extension"

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
  about:blank >/tmp/clawbench-run/chrome.log 2>&1 &
echo "$!" > /tmp/clawbench-run/chrome.pid

sleep 2
socat TCP-LISTEN:9223,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:9222 >/tmp/clawbench-run/socat.log 2>&1 &
echo "$!" > /tmp/clawbench-run/socat.pid

x11vnc -display "$DISPLAY" -nopw -shared -forever -rfbport 5900 -xkb >/tmp/clawbench-run/x11vnc.log 2>&1 &
echo "$!" > /tmp/clawbench-run/x11vnc.pid
sleep 1

/opt/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 6080 >/tmp/clawbench-run/novnc.log 2>&1 &
echo "$!" > /tmp/clawbench-run/novnc.pid

echo "$$" > /tmp/clawbench-run/runtime.pid
echo "CDP ready at http://127.0.0.1:9223"
echo "noVNC ready at http://127.0.0.1:6080/vnc.html"
