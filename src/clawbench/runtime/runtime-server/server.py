import base64
import json
import os
import re
import signal
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import urllib.request

import websocket
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

DATA_DIR = Path(os.environ.get("CLAWBENCH_DATA_DIR", "/data"))
ACTIONS_FILE = DATA_DIR / "actions.jsonl"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
RECORDING_PATH = DATA_DIR / "recording.mp4"
EVAL_SCHEMA_PATH = Path("/eval-schema.json")
REQUESTS_FILE = DATA_DIR / "requests.jsonl"
INTERCEPTION_FILE = DATA_DIR / "interception.json"

CDP_URL = os.environ.get("CLAWBENCH_BROWSER_CDP_URL", "http://127.0.0.1:9222")
RECORDING_MODE = os.environ.get("CLAWBENCH_RECORDING_MODE", "x11")
ACTION_BINDING = "__clawbenchAction"
SCREENSHOT_THROTTLE_MS = 500

ffmpeg_proc = None
eval_schema = None
eval_interceptor_ready = False


def stop_ffmpeg_recording(timeout: int = 10) -> str:
    global ffmpeg_proc
    if RECORDING_MODE == "disabled":
        return "disabled"
    if not ffmpeg_proc or ffmpeg_proc.poll() is not None:
        return "already_stopped"

    ffmpeg_proc.send_signal(signal.SIGINT)
    try:
        ffmpeg_proc.wait(timeout=timeout)
        return "stopped"
    except subprocess.TimeoutExpired:
        ffmpeg_proc.terminate()
        try:
            ffmpeg_proc.wait(timeout=3)
            return "terminated"
        except subprocess.TimeoutExpired:
            ffmpeg_proc.kill()
            ffmpeg_proc.wait(timeout=3)
            return "killed"


ACTION_CAPTURE_SCRIPT = r"""
(function () {
  "use strict";

  if (window.__clawbenchActionCaptureInstalled) return;
  window.__clawbenchActionCaptureInstalled = true;

  const THROTTLE_MS = 500;
  const lastSent = {};

  function getXPath(el) {
    if (!el || el.nodeType !== 1) return "";
    const parts = [];
    while (el && el.nodeType === 1) {
      let idx = 1;
      for (let sib = el.previousElementSibling; sib; sib = sib.previousElementSibling) {
        if (sib.tagName === el.tagName) idx++;
      }
      parts.unshift(`${el.tagName.toLowerCase()}[${idx}]`);
      el = el.parentElement;
    }
    return "/" + parts.join("/");
  }

  function classNameFor(target) {
    if (!target || target.className === undefined) return "";
    if (typeof target.className === "string") return target.className;
    if (target.className && typeof target.className.baseVal === "string") {
      return target.className.baseVal;
    }
    return String(target.className || "");
  }

  function emit(payload) {
    try {
      if (typeof window.__clawbenchAction === "function") {
        window.__clawbenchAction(JSON.stringify(payload));
      }
    } catch (_) {}
  }

  function buildPayload(type, e) {
    const target = e.target || {};
    const payload = {
      type,
      timestamp: Date.now(),
      url: location.href,
      target: {
        tagName: target.tagName || "",
        id: target.id || "",
        className: classNameFor(target),
        textContent: (target.textContent || "").slice(0, 100),
        xpath: getXPath(target),
      },
    };
    if (e.clientX !== undefined) {
      payload.x = e.clientX;
      payload.y = e.clientY;
    }
    if (e.key) payload.key = e.key;
    if (target.value !== undefined) payload.value = String(target.value).slice(0, 200);
    if (type === "scroll") {
      payload.scrollX = window.scrollX;
      payload.scrollY = window.scrollY;
    }
    return payload;
  }

  function throttled(type) {
    return type === "scroll" || type === "input";
  }

  function send(type, e) {
    if (throttled(type)) {
      const now = Date.now();
      if (lastSent[type] && now - lastSent[type] < THROTTLE_MS) return;
      lastSent[type] = now;
    }
    emit(buildPayload(type, e));
  }

  ["click", "keydown", "keyup", "input", "scroll", "change", "submit"].forEach((evt) => {
    document.addEventListener(evt, (e) => send(evt, e), true);
  });

  function sendPageLoad() {
    emit({
      type: "pageLoad",
      timestamp: Date.now(),
      url: location.href,
      title: document.title,
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sendPageLoad, { once: true });
  } else {
    setTimeout(sendPageLoad, 0);
  }
})();
"""


def _const_fields_match(expected, actual):
    """Check that all key-value pairs in expected match in actual data.
    For list bodies (batched GraphQL), returns True if any item matches.
    Returns True if all match or expected is empty/None."""
    if not expected:
        return True
    if not actual:
        return False
    if isinstance(actual, list):
        return any(_const_fields_match(expected, item) for item in actual)
    if not isinstance(actual, dict):
        return False
    return all(actual.get(k) == v for k, v in expected.items())


FILTERED_PREFIXES = (
    "http://localhost:7878",
    "http://127.0.0.1:7878",
    "chrome-extension://",
    "devtools://",
    "chrome://",
)


def _parse_body(post_data):
    """Parse postData string into a structured body (JSON dict, form dict, or raw string)."""
    if not post_data:
        return None
    try:
        return json.loads(post_data)
    except (json.JSONDecodeError, TypeError):
        try:
            parsed = parse_qs(post_data, keep_blank_values=True)
            if parsed:
                return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        except Exception:
            pass
        return post_data


def _log_request(log_file, params):
    """Log a Fetch.requestPaused event to requests.jsonl. Returns None."""
    request = params["request"]
    request_url = request["url"]

    if any(request_url.startswith(p) for p in FILTERED_PREFIXES):
        return

    parsed = urlparse(request_url)
    query_params = {
        k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()
    }

    entry = {
        "timestamp": time.time(),
        "url": request_url,
        "method": request["method"],
        "headers": request.get("headers", {}),
        "body": _parse_body(request.get("postData")),
        "query_params": query_params,
        "resource_type": params.get("resourceType", "Other"),
    }
    log_file.write(json.dumps(entry) + "\n")
    log_file.flush()


def _log_action(log_file, payload):
    """Append a browser action payload to actions.jsonl."""
    log_file.write(json.dumps(payload) + "\n")
    log_file.flush()


def start_cdp_handler(
    url_pattern=None, required_method=None, match_body=None, match_params=None
):
    """Connect to Chrome via CDP, log all requests, and optionally block by URL pattern + method + body/params."""

    # Wait for CDP to be ready. Local Chromium exposes an HTTP CDP root; remote
    # providers may hand us the browser WebSocket URL directly.
    ws = None
    for _ in range(30):
        try:
            if CDP_URL.startswith(("ws://", "wss://")):
                ws = websocket.create_connection(CDP_URL)
            else:
                version = json.loads(
                    urllib.request.urlopen(f"{CDP_URL}/json/version").read()
                )
                ws = websocket.create_connection(version["webSocketDebuggerUrl"])
            break
        except Exception:
            time.sleep(1)
    if ws is None:
        print("[cdp] CDP not available, skipping handler", flush=True)
        return

    global eval_interceptor_ready

    msg_id = [1]

    def send(method, params=None, session_id=None):
        current_id = msg_id[0]
        msg = {"id": current_id, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        ws.send(json.dumps(msg))
        msg_id[0] += 1
        return current_id

    # Auto-attach to all targets with flatten so events come on this connection.
    # waitForDebuggerOnStart=True pauses new targets until we explicitly resume
    # them, which prevents the "Debugger paused in another tab" Chrome banner
    # and ensures no requests slip through before Fetch.enable is active.
    send(
        "Target.setAutoAttach",
        {
            "autoAttach": True,
            "waitForDebuggerOnStart": True,
            "flatten": True,
        },
    )

    if url_pattern:
        eval_interceptor_ready = True
        print(f"[cdp] Interceptor connected, watching for: {url_pattern}", flush=True)
    else:
        print("[cdp] Request logger connected (no intercept pattern)", flush=True)

    # Track page sessions and async screenshot requests. Fetch handles network
    # logging/interception; Runtime bindings carry DOM action payloads back to
    # the server; Page.captureScreenshot replaces extension screenshots.
    fetch_sessions = set()
    instrumented_sessions = set()
    session_to_target = {}  # sessionId -> targetId
    active_target = [None]  # mutable ref: currently active targetId
    pending_screenshots = {}  # CDP command id -> timestamp
    last_screenshot = [0.0]
    requests_log_file = open(REQUESTS_FILE, "a")
    actions_log_file = open(ACTIONS_FILE, "a")

    def request_screenshot(session_id, timestamp):
        if not session_id:
            return
        now = time.time() * 1000
        if now - last_screenshot[0] < SCREENSHOT_THROTTLE_MS:
            return
        last_screenshot[0] = now
        screenshot_id = send(
            "Page.captureScreenshot",
            {"format": "png", "captureBeyondViewport": False},
            session_id,
        )
        pending_screenshots[screenshot_id] = timestamp

    def activate_session_target(session_id, reason):
        target_id = session_to_target.get(session_id)
        if target_id and target_id != active_target[0]:
            send("Target.activateTarget", {"targetId": target_id})
            active_target[0] = target_id
            print(
                f"[cdp] Auto-focused tab {target_id[:12]}... ({reason})",
                flush=True,
            )

    try:
        while True:
            try:
                raw = ws.recv()
            except Exception:
                break
            msg = json.loads(raw)
            session_id = msg.get("sessionId")

            if msg.get("id") in pending_screenshots:
                ts = pending_screenshots.pop(msg["id"])
                data = msg.get("result", {}).get("data")
                if data:
                    try:
                        (SCREENSHOTS_DIR / f"{ts}.png").write_bytes(
                            base64.b64decode(data)
                        )
                    except Exception as e:
                        print(f"[cdp] Screenshot write failed: {e}", flush=True)
                elif "error" in msg:
                    print(f"[cdp] Screenshot failed: {msg['error']}", flush=True)
                continue

            # When a new target attaches, enable Fetch then resume execution.
            # Because waitForDebuggerOnStart=True, the target is paused until
            # we call Runtime.runIfWaitingForDebugger — this avoids the
            # "Debugger paused in another tab" banner and ensures Fetch is
            # active before any requests fire.
            if msg.get("method") == "Target.attachedToTarget":
                child_session = msg["params"]["sessionId"]
                target_type = msg["params"]["targetInfo"]["type"]
                target_id = msg["params"]["targetInfo"]["targetId"]
                if target_type == "page":
                    session_to_target[child_session] = target_id
                    if child_session not in instrumented_sessions:
                        send("Runtime.enable", {}, child_session)
                        send("Page.enable", {}, child_session)
                        send(
                            "Runtime.addBinding",
                            {"name": ACTION_BINDING},
                            child_session,
                        )
                        send(
                            "Page.addScriptToEvaluateOnNewDocument",
                            {"source": ACTION_CAPTURE_SCRIPT},
                            child_session,
                        )
                        send(
                            "Runtime.evaluate",
                            {"expression": ACTION_CAPTURE_SCRIPT},
                            child_session,
                        )
                        instrumented_sessions.add(child_session)
                        print(
                            f"[cdp] Action capture enabled on session {child_session[:12]}...",
                            flush=True,
                        )
                    if child_session not in fetch_sessions:
                        send(
                            "Fetch.enable",
                            {
                                "patterns": [
                                    {"urlPattern": "*", "requestStage": "Request"}
                                ],
                            },
                            child_session,
                        )
                        fetch_sessions.add(child_session)
                        print(
                            f"[cdp] Fetch enabled on session {child_session[:12]}...",
                            flush=True,
                        )
                # Always resume the target so it doesn't stay paused
                send("Runtime.runIfWaitingForDebugger", {}, child_session)
                continue

            if msg.get("method") == "Runtime.bindingCalled":
                params = msg.get("params", {})
                if params.get("name") != ACTION_BINDING:
                    continue
                try:
                    payload = json.loads(params.get("payload", "{}"))
                except json.JSONDecodeError:
                    print("[cdp] Ignoring malformed action payload", flush=True)
                    continue
                activate_session_target(session_id, "action")
                _log_action(actions_log_file, payload)
                request_screenshot(
                    session_id, payload.get("timestamp", int(time.time() * 1000))
                )
                continue

            if msg.get("method") != "Fetch.requestPaused":
                if "error" in msg and msg.get("id"):
                    print(f"[cdp] CDP error: {msg['error']}", flush=True)
                continue

            params = msg["params"]
            request_url = params["request"]["url"]
            request_id = params["requestId"]

            # Auto-focus: when a page navigation (Document request) happens on a
            # background tab, bring that tab to front so the screen recording and
            # screenshots always show the tab the agent is working on.
            resource_type = params.get("resourceType", "")
            if resource_type == "Document" and session_id:
                activate_session_target(session_id, "Document request")

            # Log every non-internal request
            _log_request(requests_log_file, params)

            # If no intercept pattern, just continue the request
            if not url_pattern:
                send("Fetch.continueRequest", {"requestId": request_id}, session_id)
                continue

            # --- Intercept: block if URL + method + body/params match ---
            if not re.search(url_pattern, request_url):
                send("Fetch.continueRequest", {"requestId": request_id}, session_id)
                continue

            if required_method and params["request"]["method"] != required_method:
                send("Fetch.continueRequest", {"requestId": request_id}, session_id)
                continue

            # Parse request data for body/params matching
            parsed = urlparse(request_url)
            query_params = {
                k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()
            }
            body = _parse_body(params["request"].get("postData"))

            if not _const_fields_match(match_body, body):
                send("Fetch.continueRequest", {"requestId": request_id}, session_id)
                continue

            if not _const_fields_match(match_params, query_params):
                send("Fetch.continueRequest", {"requestId": request_id}, session_id)
                continue

            # All filters matched — block the request
            request_obj = {
                "url": request_url,
                "method": params["request"]["method"],
                "params": query_params,
                "body": body,
            }

            print(f"[interceptor] Blocked: {request_url[:100]}", flush=True)

            send(
                "Fetch.failRequest",
                {"requestId": request_id, "errorReason": "BlockedByClient"},
                session_id,
            )

            if not INTERCEPTION_FILE.exists():
                result = {
                    "intercepted": True,
                    "request": request_obj,
                    "schema": eval_schema,
                }
                INTERCEPTION_FILE.write_text(json.dumps(result, indent=2))
            try:
                urllib.request.urlopen(
                    urllib.request.Request(
                        "http://127.0.0.1:7878/api/stop", method="POST"
                    )
                )
            except Exception:
                pass
    finally:
        requests_log_file.close()
        actions_log_file.close()
        ws.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ffmpeg_proc, eval_schema
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    ACTIONS_FILE.touch(exist_ok=True)
    REQUESTS_FILE.touch(exist_ok=True)

    url_pattern = None
    required_method = None
    match_body = None
    match_params = None
    if EVAL_SCHEMA_PATH.exists():
        eval_schema = json.loads(EVAL_SCHEMA_PATH.read_text())
        url_pattern = eval_schema.get("url_pattern", "")
        if not url_pattern:
            url_pattern = None
        required_method = eval_schema.get("method")
        match_body = eval_schema.get("body")
        match_params = eval_schema.get("params")

    if RECORDING_MODE == "disabled":
        print("[recording] disabled", flush=True)
        ffmpeg_proc = None
    else:
        # Start screen recording of the Xvfb display
        display = os.environ.get("DISPLAY", ":99")
        ffmpeg_proc = subprocess.Popen(
            [
                "ffmpeg",
                "-y",
                "-f",
                "x11grab",
                "-video_size",
                "1920x1080",
                "-framerate",
                "15",
                "-i",
                display,
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "28",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+frag_keyframe+empty_moov+default_base_moof",
                str(RECORDING_PATH),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Start CDP handler: always logs requests, optionally blocks by URL pattern + method + body/params
    threading.Thread(
        target=start_cdp_handler,
        args=(url_pattern, required_method, match_body, match_params),
        daemon=True,
    ).start()

    yield

    stop_ffmpeg_recording(timeout=5)


app = FastAPI(lifespan=lifespan)


@app.get("/api/status")
async def status():
    return {"status": "ok", "eval_interceptor_ready": eval_interceptor_ready}


@app.get("/submit", response_class=HTMLResponse)
async def submit_page():
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Submit Final Answer</title>
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      background: #f6f7f9;
      color: #202124;
    }
    main {
      max-width: 820px;
      margin: 40px auto;
      padding: 0 20px;
    }
    h1 {
      font-size: 28px;
      font-weight: 650;
      margin: 0 0 16px;
    }
    textarea {
      box-sizing: border-box;
      width: 100%;
      min-height: 340px;
      resize: vertical;
      border: 1px solid #c5c9d1;
      border-radius: 6px;
      padding: 14px;
      font: 15px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      background: white;
    }
    button {
      margin-top: 14px;
      border: 0;
      border-radius: 6px;
      padding: 10px 16px;
      font-size: 15px;
      font-weight: 650;
      background: #1a73e8;
      color: white;
      cursor: pointer;
    }
    button:disabled {
      opacity: 0.65;
      cursor: default;
    }
    #status {
      margin-top: 12px;
      color: #5f6368;
    }
  </style>
</head>
<body>
  <main>
    <h1>Submit Final Answer</h1>
    <form id="answer-form">
      <textarea id="answer" name="answer" autofocus required></textarea>
      <button type="submit">Submit</button>
      <div id="status" role="status"></div>
    </form>
  </main>
  <script>
    const form = document.getElementById("answer-form");
    const answer = document.getElementById("answer");
    const status = document.getElementById("status");
    const button = form.querySelector("button");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      button.disabled = true;
      status.textContent = "Submitting...";
      try {
        await fetch("/api/task-submit", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({answer: answer.value})
        });
        status.textContent = "Submitted.";
      } catch (_) {
        status.textContent = "Submitted.";
      }
    });
  </script>
</body>
</html>"""


@app.post("/api/task-submit")
async def task_submit(data: dict):
    return {"status": "received", "answer_length": len(str(data.get("answer", "")))}


@app.post("/api/action")
async def action(data: dict):
    with open(ACTIONS_FILE, "a") as f:
        f.write(json.dumps(data) + "\n")
    return {"status": "ok"}


@app.post("/api/screenshot")
async def screenshot(data: dict):
    ts = data.get("timestamp", 0)
    img_bytes = base64.b64decode(data["data"])
    (SCREENSHOTS_DIR / f"{ts}.png").write_bytes(img_bytes)
    return {"status": "ok"}


@app.post("/api/stop")
async def stop():
    # Signal the entrypoint watchdog to kill the agent
    (DATA_DIR / ".stop-requested").touch()

    with open(ACTIONS_FILE) as f:
        actions_count = sum(1 for _ in f) if ACTIONS_FILE.exists() else 0
    screenshots_count = len(list(SCREENSHOTS_DIR.glob("*.png")))
    with open(REQUESTS_FILE) as f:
        requests_count = sum(1 for _ in f) if REQUESTS_FILE.exists() else 0

    return {
        "status": "stopped",
        "actions_count": actions_count,
        "screenshots_count": screenshots_count,
        "requests_count": requests_count,
        "has_recording": RECORDING_PATH.exists(),
    }


@app.post("/api/stop-recording")
async def stop_recording():
    status = stop_ffmpeg_recording(timeout=10)
    size = RECORDING_PATH.stat().st_size if RECORDING_PATH.exists() else 0
    return {
        "status": "recording_stopped",
        "recorder_status": status,
        "has_recording": RECORDING_PATH.exists(),
        "recording_size": size,
    }
