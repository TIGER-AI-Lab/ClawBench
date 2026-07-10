#!/usr/bin/env python3
"""Random-click baseline: dispatch N random CDP mouse clicks — a non-trivial floor.

Acts on the page but without any task intent, so it should still score ~0: it
demonstrates that browsing activity alone (without hitting the *target* action)
does not pass the interceptor.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.request

import websocket

# The shared browser CDP endpoint is always exported by the base entrypoint.
CDP = os.environ.get("CLAWBENCH_BROWSER_CDP_URL", "").rstrip("/")
N = int(os.environ.get("RANDOM_CLICK_COUNT", "20"))
ACTIONS = "/data/actions.jsonl"


def _page_ws() -> str:
    targets = json.loads(urllib.request.urlopen(f"{CDP}/json/list", timeout=10).read())
    for t in targets:
        if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
            return t["webSocketDebuggerUrl"]
    version = json.loads(
        urllib.request.urlopen(f"{CDP}/json/version", timeout=10).read()
    )
    return version["webSocketDebuggerUrl"]


def main() -> int:
    os.makedirs("/data", exist_ok=True)
    if not CDP:
        print("random-click: CLAWBENCH_BROWSER_CDP_URL not set")
        return 0
    try:
        ws = websocket.create_connection(_page_ws(), timeout=15)
    except Exception as e:  # noqa: BLE001
        print(f"random-click: could not connect to CDP ({e})")
        return 0  # a failed connect still yields a valid (0-target) run
    mid = 0

    def send(method: str, params: dict | None = None) -> None:
        nonlocal mid
        mid += 1
        ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        ws.recv()

    with open(ACTIONS, "a") as f:
        for i in range(N):
            x, y = random.randint(0, 1900), random.randint(0, 1000)
            for phase in ("mousePressed", "mouseReleased"):
                try:
                    send(
                        "Input.dispatchMouseEvent",
                        {
                            "type": phase,
                            "x": x,
                            "y": y,
                            "button": "left",
                            "clickCount": 1,
                        },
                    )
                except Exception:  # noqa: BLE001, S112
                    continue
            f.write(json.dumps({"type": "random_click", "x": x, "y": y, "i": i}) + "\n")
            f.flush()
            time.sleep(0.4)
    print(f"random-click: dispatched {N} random clicks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
