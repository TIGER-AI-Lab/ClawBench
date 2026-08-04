#!/usr/bin/env python3
"""Drive the pinned WebBrain MV3 extension through Chrome DevTools Protocol."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping


DATA_DIR = Path("/data")
TRANSCRIPT_PATH = DATA_DIR / "agent-messages.jsonl"
USAGE_PATH = DATA_DIR / "usage.jsonl"
INTERCEPTION_PATH = DATA_DIR / "interception.json"
WEBBRAIN_WORKER_RE = re.compile(
    r"^chrome-extension://([a-z]+)/src/background\.js(?:[?#].*)?$"
)


def model_config(env: Mapping[str, str]) -> dict[str, str]:
    """Validate and normalize ClawBench's model environment."""
    api_type = env.get("API_TYPE", "").strip()
    if api_type != "openai-completions":
        raise ValueError(
            f"unsupported API_TYPE for WebBrain harness: {api_type or '<missing>'}"
        )
    base_url = env.get("BASE_URL", "").strip().rstrip("/")
    if not base_url:
        raise ValueError("BASE_URL must be set")
    model = env.get("MODEL_NAME", "").strip()
    if not model:
        raise ValueError("MODEL_NAME must be set")

    keys: list[str] = []
    raw_keys = env.get("API_KEYS", "").strip()
    if raw_keys:
        try:
            parsed = json.loads(raw_keys)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            keys = [str(value).strip() for value in parsed if str(value).strip()]
    fallback = env.get("API_KEY", "").strip()
    api_key = keys[0] if keys else fallback
    if not api_key:
        raise ValueError("no API key provided (API_KEYS or API_KEY)")
    return {"api_key": api_key, "base_url": base_url, "model": model}


def webbrain_extension_id(targets: list[dict[str, Any]]) -> str:
    """Return the extension id for WebBrain's distinct service-worker path."""
    for target in targets:
        if target.get("type") != "service_worker":
            continue
        match = WEBBRAIN_WORKER_RE.match(str(target.get("url", "")))
        if match:
            return match.group(1)
    raise RuntimeError("WebBrain service worker did not appear in CDP targets")


def _to_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    try:
        return max(int(float(value)), 0)
    except (TypeError, ValueError):
        return 0


def _first_int(data: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = _to_int(data.get(key))
        if value:
            return value
    return 0


def usage_rows(
    traces: list[dict[str, Any]], fallback_model: str
) -> list[dict[str, Any]]:
    """Convert WebBrain trace usage into ClawBench's non-overlapping token rows."""
    rows: list[dict[str, Any]] = []
    for trace_entry in traces:
        run = trace_entry.get("run") or {}
        run_id = str(run.get("runId") or "unknown-run")
        for event in trace_entry.get("events") or []:
            if event.get("kind") != "llm_response":
                continue
            data = event.get("data") or {}
            raw = data.get("usage")
            if not isinstance(raw, dict):
                continue
            input_details = raw.get("prompt_tokens_details") or raw.get(
                "input_tokens_details"
            )
            if not isinstance(input_details, dict):
                input_details = {}
            output_details = raw.get("completion_tokens_details") or raw.get(
                "output_tokens_details"
            )
            if not isinstance(output_details, dict):
                output_details = {}
            cache_read = _first_int(
                raw, "cache_read_input_tokens", "cache_read_tokens", "cacheRead"
            ) or _first_int(input_details, "cached_tokens", "cache_read_tokens")
            input_tokens = _first_int(raw, "prompt_tokens", "input_tokens", "input")
            if cache_read and not _first_int(
                raw, "cache_read_input_tokens", "cache_read_tokens", "cacheRead"
            ):
                input_tokens = max(input_tokens - cache_read, 0)
            output_tokens = _first_int(
                raw, "completion_tokens", "output_tokens", "output"
            )
            cache_write = _first_int(
                raw,
                "cache_creation_input_tokens",
                "cache_write_input_tokens",
                "cache_write_tokens",
                "cacheWrite",
            )
            reasoning = _first_int(
                raw, "reasoning_tokens", "internal_reasoning_tokens"
            ) or _first_int(output_details, "reasoning_tokens")
            total = input_tokens + output_tokens + cache_read + cache_write + reasoning
            if total == 0:
                total = _first_int(raw, "total_tokens", "totalTokens", "total")
            if total == 0:
                continue
            seq = event.get("seq", "unknown")
            rows.append(
                {
                    "type": "usage",
                    "source_harness": "webbrain",
                    "call_id": f"{run_id}:{seq}",
                    "model": str(
                        data.get("model") or run.get("model") or fallback_model
                    ),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_read_tokens": cache_read,
                    "cache_write_tokens": cache_write,
                    "reasoning_tokens": reasoning,
                    "total_tokens": total,
                    "estimated_cost_usd": None,
                    "cost_status": "price_unavailable",
                }
            )
    return rows


def transcript_rows(
    instruction: str,
    result: Mapping[str, Any],
    traces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a stable JSONL transcript from WebBrain's response and trace records."""
    rows: list[dict[str, Any]] = [
        {"type": "user", "content": instruction, "role": "user"}
    ]
    for update in result.get("updates") or []:
        rows.append({"type": "agent_update", "update": update})
    for trace_entry in traces:
        run = trace_entry.get("run") or {}
        for event in trace_entry.get("events") or []:
            rows.append(
                {
                    "type": "webbrain_trace",
                    "run": run,
                    "trace": event,
                }
            )
    rows.append(
        {
            "type": "assistant",
            "role": "assistant",
            "content": str(result.get("content") or ""),
            "conversation_id": result.get("conversationId"),
            **({"error": result["error"]} if result.get("error") else {}),
        }
    )
    return rows


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            handle.flush()


def _http_json(url: str, *, method: str = "GET") -> Any:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _targets(cdp_url: str) -> list[dict[str, Any]]:
    value = _http_json(f"{cdp_url.rstrip('/')}/json/list")
    if not isinstance(value, list):
        raise RuntimeError("CDP /json/list returned a non-list response")
    return value


def _wait_for_extension_id(cdp_url: str, timeout: float = 30) -> str:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return webbrain_extension_id(_targets(cdp_url))
        except (OSError, RuntimeError) as error:
            last_error = error
            time.sleep(0.5)
    raise RuntimeError(
        "WebBrain service worker was not ready after 30s"
    ) from last_error


def _open_extension_page(cdp_url: str, extension_id: str) -> dict[str, Any]:
    page_url = f"chrome-extension://{extension_id}/src/ui/settings.html"
    encoded = urllib.parse.quote(page_url, safe="")
    target = _http_json(f"{cdp_url.rstrip('/')}/json/new?{encoded}", method="PUT")
    if not isinstance(target, dict) or not target.get("webSocketDebuggerUrl"):
        raise RuntimeError("CDP did not return a debuggable WebBrain extension page")
    return target


class CdpPage:
    """Small synchronous CDP client for one extension-page target."""

    def __init__(self, websocket_url: str, timeout: float) -> None:
        import websocket

        self._socket = websocket.create_connection(websocket_url, timeout=timeout)
        self._next_id = 0

    def close(self) -> None:
        self._socket.close()

    def evaluate(self, expression: str) -> Any:
        self._next_id += 1
        request_id = self._next_id
        self._socket.send(
            json.dumps(
                {
                    "id": request_id,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "awaitPromise": True,
                        "returnByValue": True,
                    },
                }
            )
        )
        while True:
            response = json.loads(self._socket.recv())
            if response.get("id") != request_id:
                continue
            if response.get("error"):
                raise RuntimeError(f"CDP Runtime.evaluate failed: {response['error']}")
            payload = response.get("result") or {}
            if payload.get("exceptionDetails"):
                detail = payload["exceptionDetails"].get("text", "JavaScript error")
                raise RuntimeError(f"WebBrain extension evaluation failed: {detail}")
            remote = payload.get("result") or {}
            if remote.get("subtype") == "error":
                raise RuntimeError(str(remote.get("description") or "JavaScript error"))
            return remote.get("value")


def webbrain_storage_config(config: Mapping[str, str]) -> dict[str, Any]:
    """Map a ClawBench model onto WebBrain's persisted provider contract."""
    return {
        "providers": {
            "clawbench": {
                "type": "openai",
                "category": "cloud",
                "label": "ClawBench",
                "providerName": "clawbench",
                "baseUrl": config["base_url"],
                "model": config["model"],
                "contextWindow": 200000,
                # ClawBench model configs do not declare vision capability.
                # Stay text/tool-only instead of sending image blocks to an
                # endpoint that may reject them.
                "supportsVision": False,
                "supportsTools": True,
                "supportsAskStreaming": True,
                "supportsStreamUsageOptions": False,
                "apiKey": config["api_key"],
                "enabled": True,
                "configured": True,
            }
        },
        "activeProvider": "clawbench",
        "tracingEnabled": True,
        # ClawBench runs are unattended. The task instruction supplies the
        # authorization while the request interceptor remains the final
        # boundary for consequential submissions.
        "onboardingComplete": True,
        "askBeforeConsequentialActions": False,
        "planBeforeActMode": "try",
        "planReviewMode": "never",
        # WebBrain's supported Instant setting. The benchmark instruction is
        # the user authorization; ClawBench's interceptor remains the final
        # boundary for consequential network requests.
        "clarifyTimeoutSec": 0,
        "clarifyTimeoutSemanticsV2": True,
    }


def stop_request_reason(interception_path: Path = INTERCEPTION_PATH) -> str:
    """Classify a runtime stop marker without assuming it was an eval match."""
    try:
        interception = json.loads(interception_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "stop_requested"
    return (
        "eval_matched" if interception.get("intercepted") is True else "stop_requested"
    )


def _configuration_expression(config: Mapping[str, str]) -> str:
    stored = webbrain_storage_config(config)
    return (
        "(async()=>{await chrome.storage.local.set("
        + json.dumps(stored, separators=(",", ":"))
        + ");await new Promise(r=>setTimeout(r,500));return {ok:true};})()"
    )


def _chat_expression(instruction: str) -> str:
    payload = json.dumps(instruction)
    return f"""
(async()=>{{
  const tabs=await chrome.tabs.query({{}});
  const candidates=tabs.filter(t=>t.id&&!(t.url||'').startsWith('chrome-extension://')&&!(t.url||'').startsWith('devtools://'));
  const tab=candidates.find(t=>t.active)||candidates[0];
  if(!tab) return {{error:'No task tab available'}};
  const response=await new Promise(resolve=>chrome.runtime.sendMessage(
    {{target:'background',action:'chat',tabId:tab.id,text:{payload},mode:'act',foreground:true}},
    value=>{{const error=chrome.runtime.lastError;resolve(error?{{error:error.message}}:value);}}
  ));
  return response||{{error:'WebBrain returned an empty response'}};
}})()
"""


def _trace_expression(conversation_id: str) -> str:
    conversation = json.dumps(conversation_id)
    return f"""
(async()=>{{
  await new Promise(r=>setTimeout(r,500));
  const open=()=>new Promise((resolve,reject)=>{{const q=indexedDB.open('webbrain_traces');q.onsuccess=()=>resolve(q.result);q.onerror=()=>reject(q.error);}});
  const all=store=>new Promise((resolve,reject)=>{{const q=store.getAll();q.onsuccess=()=>resolve(q.result||[]);q.onerror=()=>reject(q.error);}});
  const db=await open();
  for(let attempt=0;attempt<20;attempt++){{
    const runs=(await all(db.transaction('runs','readonly').objectStore('runs'))).filter(r=>r.conversationId==={conversation});
    const output=[];
    for(const run of runs){{
      const tx=db.transaction('events','readonly');
      const index=tx.objectStore('events').index('runId');
      const events=await new Promise((resolve,reject)=>{{const q=index.getAll(IDBKeyRange.only(run.runId));q.onsuccess=()=>resolve(q.result||[]);q.onerror=()=>reject(q.error);}});
      output.push({{run,events}});
    }}
    if(output.length&&output.every(x=>x.run.endedAt)) return output;
    await new Promise(r=>setTimeout(r,250));
  }}
  return [];
}})()
"""


def main() -> int:
    config = model_config(os.environ)
    instruction = os.environ.get("INSTRUCTION", "").strip()
    if not instruction:
        raise ValueError("INSTRUCTION must be set")
    cdp_url = os.environ.get("CLAWBENCH_BROWSER_CDP_URL", "").strip().rstrip("/")
    if not cdp_url:
        raise ValueError("CLAWBENCH_BROWSER_CDP_URL must be set")
    max_wait = float(os.environ.get("TIME_LIMIT_S", "1800")) + 60

    # Persist the authoritative task before the long-running extension call so
    # an interceptor/watchdog stop still leaves a useful partial transcript.
    _append_jsonl(
        TRANSCRIPT_PATH,
        [{"type": "user", "content": instruction, "role": "user"}],
    )

    extension_id = _wait_for_extension_id(cdp_url)
    target = _open_extension_page(cdp_url, extension_id)
    page = CdpPage(str(target["webSocketDebuggerUrl"]), timeout=max_wait)
    try:
        page.evaluate(_configuration_expression(config))
        result = page.evaluate(_chat_expression(instruction))
        if not isinstance(result, dict):
            result = {"error": "WebBrain returned a non-object response"}
        traces: list[dict[str, Any]] = []
        conversation_id = result.get("conversationId")
        if conversation_id:
            raw_traces = page.evaluate(_trace_expression(str(conversation_id)))
            if isinstance(raw_traces, list):
                traces = raw_traces
        _append_jsonl(
            TRANSCRIPT_PATH,
            transcript_rows(instruction, result, traces)[1:],
        )
        _append_jsonl(USAGE_PATH, usage_rows(traces, config["model"]))
        if result.get("error"):
            raise RuntimeError(str(result["error"]))
        print(str(result.get("content") or ""))
        return 0
    except Exception as error:
        _append_jsonl(
            TRANSCRIPT_PATH,
            [{"type": "error", "source_harness": "webbrain", "error": str(error)}],
        )
        raise
    finally:
        page.close()


if __name__ == "__main__":
    if sys.argv[1:] == ["--classify-stop-request"]:
        print(stop_request_reason())
        raise SystemExit(0)
    raise SystemExit(main())
