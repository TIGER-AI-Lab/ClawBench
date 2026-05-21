#!/bin/bash
set -e

# Runtime harness for Claude Code CLI + Claude in Chrome extension.
#
# Depends on three local servers that come up before the agent:
#   1. LiteLLM proxy on :4000 — translates /v1/messages to whatever provider
#      models.yaml points at (same pattern as the regular claude-code harness).
#   2. Mock Anthropic meta API on :4001 — returns canned profile / org /
#      settings responses for the ~46 hardcoded `api.anthropic.com/api/*`
#      calls cli.js makes at startup (rewritten to 127.0.0.1:4001 at build).
#   3. Fake session bridge on :4002 — local stand-in for
#      `wss://bridge.claudeusercontent.com`; rendezvous point where the CLI
#      and the Claude-in-Chrome extension meet to relay tool_calls.
#
# The CLI's isInteractive gate for --chrome is force-passed via a cli.js
# patch (see patch-claude-cli.py), so we invoke claude in the usual
# `-p --output-format stream-json` mode and get a normal transcript on
# stdout — no pty wrapper needed.

/setup-claude-code-chrome-extension.sh
source /tmp/claude-code-env.sh

# --- LiteLLM translation proxy ----------------------------------------------
echo "Starting API translation proxy (litellm)..."
LITELLM_PORT=4003
litellm --config /tmp/litellm-config.yaml --port "$LITELLM_PORT" \
  > /data/proxy.log 2>&1 &
PROXY_PID=$!
for i in $(seq 1 30); do
  if curl -sf "http://localhost:${LITELLM_PORT}/health/liveliness" > /dev/null 2>&1; then
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

# Keep Claude Code pointed at localhost:4000, but put a narrow retrying
# wrapper in front of LiteLLM. OpenRouter sometimes returns a transient 429
# with "No deployments available ... Try again in 5 seconds"; without this,
# Claude sees the first failure and exits the whole run.
cat > /tmp/retry-litellm-proxy.py <<'PYEOF'
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("RETRY_PROXY_UPSTREAM", "http://127.0.0.1:4003").rstrip("/")
MAX_RETRIES = int(os.environ.get("RETRY_PROXY_MAX_RETRIES", "10"))
BASE_DELAY = float(os.environ.get("RETRY_PROXY_BASE_DELAY", "5"))
MAX_DELAY = float(os.environ.get("RETRY_PROXY_MAX_DELAY", "60"))
TIMEOUT = float(os.environ.get("RETRY_PROXY_TIMEOUT", "1800"))

HOP_BY_HOP_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

TRANSIENT_PHRASES = (
    "no deployments available",
    "temporarily limiting requests",
    "try again in",
    "rate limit",
    "rate_limit",
)
TEXT_ONLY_AFTER_IMAGE_REJECTION = False


def log(message: str) -> None:
    print(f"[retry-proxy] {message}", file=sys.stderr, flush=True)


def retry_after(headers) -> float | None:
    value = headers.get("Retry-After") if headers else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def should_retry(status: int, body: bytes) -> bool:
    if status in {408, 409, 425, 429, 500, 502, 503, 504}:
        return True
    snippet = body[:8192].decode("utf-8", "ignore").lower()
    return any(phrase in snippet for phrase in TRANSIENT_PHRASES)


def looks_like_image_rejection(status: int, body: bytes) -> bool:
    if status not in {400, 404, 415, 422}:
        return False
    snippet = body[:8192].decode("utf-8", "ignore").lower()
    return (
        ("image" in snippet or "vision" in snippet or "multimodal" in snippet)
        or ("model" in snippet and ("not exist" in snippet or "not found" in snippet))
        or "not support" in snippet
        or "unsupported" in snippet
    )


def strip_image_blocks(value):
    if isinstance(value, dict):
        if value.get("type") == "image":
            return {
                "type": "text",
                "text": (
                    "[screenshot image omitted by harness proxy because this "
                    "model route rejected image content]"
                ),
            }, True
        changed = False
        cleaned = {}
        for key, item in value.items():
            new_item, item_changed = strip_image_blocks(item)
            cleaned[key] = new_item
            changed = changed or item_changed
        return cleaned, changed
    if isinstance(value, list):
        changed = False
        cleaned = []
        for item in value:
            new_item, item_changed = strip_image_blocks(item)
            cleaned.append(new_item)
            changed = changed or item_changed
        return cleaned, changed
    return value, False


def image_stripped_body(path: str, body: bytes | None) -> tuple[bytes | None, bool]:
    if not body or not path.startswith("/v1/messages"):
        return body, False
    try:
        payload = json.loads(body)
    except Exception:
        return body, False
    cleaned, changed = strip_image_blocks(payload)
    if not changed:
        return body, False
    return json.dumps(cleaned, separators=(",", ":")).encode(), True


class RetryProxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        log(fmt % args)

    def do_GET(self) -> None:
        if self.path in {"/health/liveliness", "/health/readiness"}:
            body = b'{"status":"ok"}\n'
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.forward()

    def do_POST(self) -> None:
        self.forward()

    def do_PUT(self) -> None:
        self.forward()

    def do_PATCH(self) -> None:
        self.forward()

    def do_DELETE(self) -> None:
        self.forward()

    def forward(self) -> None:
        global TEXT_ONLY_AFTER_IMAGE_REJECTION
        body_len = int(self.headers.get("content-length") or 0)
        original_body = self.rfile.read(body_len) if body_len else None
        fallback_body, has_image_fallback = image_stripped_body(self.path, original_body)
        image_fallback_used = TEXT_ONLY_AFTER_IMAGE_REJECTION and has_image_fallback
        body = fallback_body if image_fallback_used else original_body
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
        }
        url = f"{UPSTREAM}{self.path}"

        final_status = 502
        final_headers = {}
        final_body = b""
        for attempt in range(MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers=headers,
                    method=self.command,
                )
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    final_status = resp.status
                    final_headers = dict(resp.headers.items())
                    final_body = resp.read()
            except urllib.error.HTTPError as exc:
                final_status = exc.code
                final_headers = dict(exc.headers.items())
                final_body = exc.read()
            except Exception as exc:
                final_status = 502
                final_headers = {"content-type": "application/json"}
                final_body = json.dumps({"error": str(exc)}).encode()

            if (
                has_image_fallback
                and not image_fallback_used
                and looks_like_image_rejection(final_status, final_body)
            ):
                image_fallback_used = True
                TEXT_ONLY_AFTER_IMAGE_REJECTION = True
                body = fallback_body
                log(
                    f"retrying {self.command} {self.path} without screenshot "
                    f"image blocks after status={final_status}"
                )
                continue

            if attempt >= MAX_RETRIES or not should_retry(final_status, final_body):
                break

            hinted = retry_after(final_headers)
            delay = hinted if hinted is not None else min(MAX_DELAY, BASE_DELAY * (2 ** attempt))
            log(
                f"retrying {self.command} {self.path}: status={final_status} "
                f"attempt={attempt + 1}/{MAX_RETRIES} delay={delay:.1f}s"
            )
            time.sleep(delay)

        self.send_response(final_status)
        for key, value in final_headers.items():
            if key.lower() in HOP_BY_HOP_HEADERS:
                continue
            self.send_header(key, value)
        self.send_header("content-length", str(len(final_body)))
        self.end_headers()
        self.wfile.write(final_body)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 4000), RetryProxy)
    log(f"listening on 127.0.0.1:4000; upstream={UPSTREAM}; retries={MAX_RETRIES}")
    server.serve_forever()


if __name__ == "__main__":
    main()
PYEOF

echo "Starting retry wrapper for API proxy..."
RETRY_PROXY_UPSTREAM="http://127.0.0.1:${LITELLM_PORT}" \
RETRY_PROXY_MAX_RETRIES="${RETRY_PROXY_MAX_RETRIES:-10}" \
RETRY_PROXY_BASE_DELAY="${RETRY_PROXY_BASE_DELAY:-5}" \
RETRY_PROXY_MAX_DELAY="${RETRY_PROXY_MAX_DELAY:-60}" \
python3 /tmp/retry-litellm-proxy.py > /data/retry-proxy.log 2>&1 &
RETRY_PROXY_PID=$!
for i in $(seq 1 15); do
  if curl -sf http://localhost:4000/health/liveliness > /dev/null 2>&1; then
    echo "Retry wrapper ready"
    break
  fi
  if [ "$i" -eq 15 ]; then
    echo "Retry wrapper not ready after 15s — check /data/retry-proxy.log"
    echo "proxy_failed" > /data/.stop-reason
    kill "$PROXY_PID" 2>/dev/null || true
    exit 1
  fi
  sleep 1
done

# --- Mock Anthropic meta API (profile/bootstrap/etc.) -----------------------
# The CLI's interactive path hits `https://api.anthropic.com/api/*` with a
# hardcoded URL (not ANTHROPIC_BASE_URL). cli.js has been rewritten at build
# time to point at 127.0.0.1:4001; we serve canned responses here.
echo "Starting Anthropic meta-API mock..."
python3 /usr/local/bin/mock-anthropic-api.py > /data/mock-api.log 2>&1 &
MOCK_PID=$!
for i in $(seq 1 15); do
  if curl -sf http://127.0.0.1:4001/api/hello > /dev/null 2>&1; then
    echo "Mock API ready"
    break
  fi
  if [ "$i" -eq 15 ]; then
    echo "Mock API not ready after 15s — check /data/mock-api.log"
    echo "mock_api_failed" > /data/.stop-reason
    kill "$RETRY_PROXY_PID" "$PROXY_PID" 2>/dev/null || true
    exit 1
  fi
  sleep 1
done

# --- Fake Anthropic session bridge (CLI ↔ extension rendezvous) --------------
# Replaces `wss://bridge.claudeusercontent.com/chrome/<user>` with a local
# WebSocket on 127.0.0.1:4002. cli.js + /app/claude-in-chrome/assets/*.js have
# been patched at build time to point here. The server speaks just enough of
# the protocol to pair one CLI with one extension and relay tool_call /
# tool_result / permission_request / ping-pong between them.
echo "Starting fake Anthropic session bridge..."
python3 /usr/local/bin/fake-anthropic-bridge.py > /data/bridge.log 2>&1 &
BRIDGE_PID=$!
for i in $(seq 1 15); do
  # Use a proper WebSocket client probe so we don't leave a "400 Bad Request"
  # line in bridge.log from a bare TCP connect. The probe opens a handshake
  # and immediately closes on success.
  if python3 -c 'import asyncio, websockets
async def p():
    async with websockets.connect("ws://127.0.0.1:4002/healthz") as ws:
        pass
asyncio.run(p())' 2>/dev/null; then
    echo "Fake bridge ready"
    break
  fi
  if [ "$i" -eq 15 ]; then
    echo "Fake bridge not ready after 15s — check /data/bridge.log"
    echo "bridge_failed" > /data/.stop-reason
    kill "$MOCK_PID" "$RETRY_PROXY_PID" "$PROXY_PID" 2>/dev/null || true
    exit 1
  fi
  sleep 1
done

# --- Workspace prep ---------------------------------------------------------
WORKSPACE=/root/workspace
mkdir -p "$WORKSPACE"
if [ -d /my-info ]; then
  cp -r /my-info "$WORKSPACE/my-info"
  echo "Copied /my-info to $WORKSPACE/my-info"
fi

# --- Wait for Edge CDP (extension-server's request interception depends on
#     it, and the Chrome extension's service worker must be up before the
#     CLI's --chrome-native-host shim is spawned) ----------------------------
echo "Waiting for Edge CDP..."
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:9222/json/version > /dev/null 2>&1; then
    echo "Edge CDP ready"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "Edge CDP not ready after 30s, aborting"
    echo "chrome_cdp_timeout" > /data/.stop-reason
    exit 1
  fi
  sleep 1
done

# --- Auth preflight --------------------------------------------------------
if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "ERROR: ANTHROPIC_API_KEY missing — /setup-... failed to source?"
  echo "chrome_auth_missing" > /data/.stop-reason
  kill "$RETRY_PROXY_PID" "$PROXY_PID" 2>/dev/null || true
  exit 1
fi

# --- Dangerous-command lockdown --------------------------------------------
# Same allowlist as every other claude-family harness.
SAFE_BIN=/tmp/safe-bin
mkdir -p "$SAFE_BIN"
for cmd in ls cat find file jq cut uniq head tail tr wc grep sort sh bash; do
  [ -x "$(command -v "$cmd" 2>/dev/null)" ] && ln -sf "$(command -v "$cmd")" "$SAFE_BIN/$cmd"
done
ln -sf "$(command -v claude)"   "$SAFE_BIN/claude"
ln -sf "$(command -v node)"     "$SAFE_BIN/node"
ln -sf "$(command -v npx)"      "$SAFE_BIN/npx"
ln -sf "$(command -v npm)"      "$SAFE_BIN/npm"

# --- Run the agent ----------------------------------------------------------
# --chrome turns on Claude-in-Chrome — the cli.js OV() patch is what lets the
# MCP server register without a TTY in -p mode. --thinking enabled maps from
# any non-"off" THINKING_LEVEL, mirroring the regular claude-code harness.
export IS_SANDBOX=1
export TERM=xterm-256color
# The pinned @anthropic-ai/claude-code@2.1.110 tries to self-update to the
# native installer on first run, which wipes our patched cli.js (i7()
# subscription gate, BASE_API_URL rewrite) and replaces it with a compiled
# native binary we can't touch. Disable the auto-updater so the patches stay
# in effect.
export DISABLE_AUTOUPDATER=1
export CLAUDE_CODE_DISABLE_AUTOUPDATER=1
export CLAUDE_CODE_DISABLE_NATIVE_INSTALLER=1
# Tell the claude-in-chrome MCP to skip its OAuth-token fetch and use a
# placeholder dev user id when opening the (redirected) session bridge
# WebSocket. LOCAL_BRIDGE=1 flips NeY() → true inside cli.js, which injects
# `devUserId: "dev_user_local"` into bridgeConfig so the `connect()` path
# takes `if (_.devUserId)` and sends `{dev_user_id: ...}` instead of
# fetching an OAuth token that doesn't exist.
export LOCAL_BRIDGE=1
export CLAUDE_CODE_DEV_USER_ID=clawbench-dev
cd "$WORKSPACE"
echo "Starting Claude Code agent (model=${MODEL_NAME}, --chrome stream-json mode)..."

# Back to `-p` print + stream-json now that cli.js has OV() force-true: the
# claude-in-chrome MCP server no longer depends on a TTY, and print mode
# skips the interactive-only startup calls (subscription profile fetch,
# OAuth info, marketplace fetch, …) that would otherwise need their own
# bypasses. Transcript streams straight to /data/agent-messages.jsonl like
# the regular claude-code harness.
CLAUDE_ARGS=(-p --verbose --output-format stream-json --model "$MODEL_NAME" --dangerously-skip-permissions --chrome)
case "${THINKING_LEVEL:-off}" in
  ""|off)  ;;
  *)       CLAUDE_ARGS+=(--thinking enabled) ;;
esac
CLAUDE_ARGS+=(-- "$INSTRUCTION")

PATH="$SAFE_BIN" claude "${CLAUDE_ARGS[@]}" \
  > /data/agent-messages.jsonl 2> /data/agent.log &
AGENT_PID=$!
sleep 3

# --- Watchdog ---------------------------------------------------------------
# Same contract as run-claude-code.sh: the CLI self-exits in -p mode when the
# response finishes (→ agent_exited), the eval interceptor can short-circuit
# via /data/.stop-requested (→ eval_matched), or we hit the idle/time-limit
# thresholds (→ agent_idle / time_limit_exceeded).
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

if [ -z "$STOP_REASON" ]; then
  if ! kill -0 "$AGENT_PID" 2>/dev/null; then
    STOP_REASON="agent_exited"
  else
    echo "Time limit (${MAX_WAIT}s) exceeded, killing agent."
    STOP_REASON="time_limit_exceeded"
  fi
fi

echo "$STOP_REASON" > /data/.stop-reason

# --- Cleanup ----------------------------------------------------------------
# The native-host subprocess is parented to Edge, the claude-in-chrome-mcp
# subprocess is parented to the agent; both need an explicit pkill after we
# take down the direct children.
kill "$AGENT_PID"  2>/dev/null || true
kill "$RETRY_PROXY_PID" 2>/dev/null || true
kill "$PROXY_PID"  2>/dev/null || true
kill "$MOCK_PID"   2>/dev/null || true
kill "$BRIDGE_PID" 2>/dev/null || true
pkill -f "@anthropic-ai/claude-code" 2>/dev/null || true
pkill -f "chrome-native-host"         2>/dev/null || true
pkill -f "claude-in-chrome-mcp"       2>/dev/null || true
pkill -f "litellm"                    2>/dev/null || true
pkill -f "mock-anthropic-api"         2>/dev/null || true
pkill -f "fake-anthropic-bridge"      2>/dev/null || true
sleep 2

curl -sf -X POST http://localhost:7878/api/stop || true
rm -f /data/.stop-requested

echo "Agent finished, recording grace period (15s)..."
sleep 15

echo "Stopping recording..."
curl -sf -X POST http://localhost:7878/api/stop-recording || true
sleep 2
rm -f /data/*.log
echo "Done."
