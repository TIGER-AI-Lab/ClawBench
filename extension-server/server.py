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

DATA_DIR = Path(os.environ.get("CLAWBENCH_DATA_DIR", "/data"))
ACTIONS_FILE = DATA_DIR / "actions.jsonl"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
RECORDING_PATH = DATA_DIR / "recording.mp4"
EVAL_SCHEMA_PATH = Path("/eval-schema.json")
REQUESTS_FILE = DATA_DIR / "requests.jsonl"
INTERCEPTION_FILE = DATA_DIR / "interception.json"

CDP_URL = "http://127.0.0.1:9222"

ffmpeg_proc = None
eval_schema = None
eval_interceptor_ready = False


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
    "http://localhost:7878", "http://127.0.0.1:7878",
    "chrome-extension://", "devtools://", "chrome://",
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
    query_params = {k: v[0] if len(v) == 1 else v
                    for k, v in parse_qs(parsed.query).items()}

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


def start_cdp_handler(url_pattern=None, required_method=None,
                      match_body=None, match_params=None):
    """Connect to Chrome via CDP, log all requests, and optionally block by URL pattern + method + body/params."""

    # Wait for Chrome CDP to be ready
    ws_url = None
    for _ in range(30):
        try:
            version = json.loads(urllib.request.urlopen(
                f"{CDP_URL}/json/version").read())
            ws_url = version["webSocketDebuggerUrl"]
            break
        except Exception:
            time.sleep(1)
    if not ws_url:
        print("[cdp] CDP not available, skipping handler", flush=True)
        return

    global eval_interceptor_ready

    ws = websocket.create_connection(ws_url)
    msg_id = [1]

    def send(method, params=None, session_id=None):
        msg = {"id": msg_id[0], "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        ws.send(json.dumps(msg))
        msg_id[0] += 1

    # Auto-attach to all targets with flatten so events come on this connection.
    # waitForDebuggerOnStart=True pauses new targets until we explicitly resume
    # them, which prevents the "Debugger paused in another tab" Chrome banner
    # and ensures no requests slip through before Fetch.enable is active.
    send("Target.setAutoAttach", {
        "autoAttach": True,
        "waitForDebuggerOnStart": True,
        "flatten": True,
    })

    if url_pattern:
        eval_interceptor_ready = True
        print(f"[cdp] Interceptor connected, watching for: {url_pattern}", flush=True)
    else:
        print("[cdp] Request logger connected (no intercept pattern)", flush=True)

    # Track sessions where Fetch is enabled, and map sessions to target IDs
    # so we can bring the correct tab to front when it receives activity.
    fetch_sessions = set()
    session_to_target = {}  # sessionId -> targetId
    active_target = [None]  # mutable ref: currently active targetId
    log_file = open(REQUESTS_FILE, "a")

    try:
        while True:
            try:
                raw = ws.recv()
            except Exception:
                break
            msg = json.loads(raw)
            session_id = msg.get("sessionId")

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
                    if child_session not in fetch_sessions:
                        send("Fetch.enable", {
                            "patterns": [{"urlPattern": "*", "requestStage": "Request"}],
                        }, child_session)
                        fetch_sessions.add(child_session)
                        print(
                            f"[cdp] Fetch enabled on session {child_session[:12]}...", flush=True)
                # Always resume the target so it doesn't stay paused
                send("Runtime.runIfWaitingForDebugger", {}, child_session)
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
                target_id = session_to_target.get(session_id)
                if target_id and target_id != active_target[0]:
                    send("Target.activateTarget", {"targetId": target_id})
                    active_target[0] = target_id
                    print(f"[cdp] Auto-focused tab {target_id[:12]}... (Document request)", flush=True)

            # Log every non-internal request
            _log_request(log_file, params)

            # If no intercept pattern, just continue the request
            if not url_pattern:
                send("Fetch.continueRequest", {
                     "requestId": request_id}, session_id)
                continue

            # --- Intercept: block if URL + method + body/params match ---
            if not re.search(url_pattern, request_url):
                send("Fetch.continueRequest", {
                     "requestId": request_id}, session_id)
                continue

            if required_method and params["request"]["method"] != required_method:
                send("Fetch.continueRequest", {
                     "requestId": request_id}, session_id)
                continue

            # Parse request data for body/params matching
            parsed = urlparse(request_url)
            query_params = {k: v[0] if len(
                v) == 1 else v for k, v in parse_qs(parsed.query).items()}
            body = _parse_body(params["request"].get("postData"))

            if not _const_fields_match(match_body, body):
                send("Fetch.continueRequest", {
                     "requestId": request_id}, session_id)
                continue

            if not _const_fields_match(match_params, query_params):
                send("Fetch.continueRequest", {
                     "requestId": request_id}, session_id)
                continue

            # All filters matched — block the request
            request_obj = {
                "url": request_url,
                "method": params["request"]["method"],
                "params": query_params,
                "body": body,
            }

            print(f"[interceptor] Blocked: {request_url[:100]}", flush=True)

            send("Fetch.failRequest", {
                 "requestId": request_id, "errorReason": "BlockedByClient"}, session_id)

            if not INTERCEPTION_FILE.exists():
                result = {"intercepted": True, "request": request_obj,
                          "schema": eval_schema}
                INTERCEPTION_FILE.write_text(json.dumps(result, indent=2))
            try:
                urllib.request.urlopen(urllib.request.Request(
                    "http://127.0.0.1:7878/api/stop", method="POST"))
            except Exception:
                pass
    finally:
        log_file.close()
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

    # Start screen recording of the Xvfb display
    display = os.environ.get("DISPLAY", ":99")
    ffmpeg_proc = subprocess.Popen(
        [
            "ffmpeg", "-y",
            "-f", "x11grab",
            "-video_size", "1920x1080",
            "-framerate", "15",
            "-i", display,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            str(RECORDING_PATH),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Start CDP handler: always logs requests, optionally blocks by URL pattern + method + body/params
    threading.Thread(target=start_cdp_handler,
                     args=(url_pattern, required_method, match_body, match_params),
                     daemon=True).start()

    yield

    if ffmpeg_proc and ffmpeg_proc.poll() is None:
        ffmpeg_proc.send_signal(signal.SIGINT)
        ffmpeg_proc.wait(timeout=5)


app = FastAPI(lifespan=lifespan)


@app.get("/api/status")
async def status():
    return {"status": "ok", "eval_interceptor_ready": eval_interceptor_ready}


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
    global ffmpeg_proc
    if ffmpeg_proc and ffmpeg_proc.poll() is None:
        ffmpeg_proc.send_signal(signal.SIGINT)
        ffmpeg_proc.wait(timeout=10)
    return {"status": "recording_stopped", "has_recording": RECORDING_PATH.exists()}
