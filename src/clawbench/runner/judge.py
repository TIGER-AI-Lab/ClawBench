"""LLM judge for ClawBench: decide if an intercepted HTTP request fulfills the instruction.

Stage 2 of the two-stage scoring rubric:
  Stage 1 — request matches eval_schema regex+method (set by interceptor → run-meta.intercepted).
  Stage 2 — judge: given task instruction + intercepted request body, does the request
            actually do what the user asked?

Final pass = stage1 AND stage2.

Uses only stdlib (urllib.request) so no extra deps. Loads model config from models.yaml
the same way run.py does, supports api_type in
{openai-completions, openai-responses, anthropic-messages}.
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from typing import Any


JUDGE_SYSTEM = """You are a strict evaluator for a web-agent benchmark.

A user gave a natural-language INSTRUCTION to an autonomous browser agent.
The agent navigated a real website and finally produced a single HTTP request
(URL + method + body) that we INTERCEPTED before it was sent to the server.

Decide whether this intercepted request, if it had been sent, would correctly
fulfill the user's instruction.

Rules:
- Match = the request would do what the user asked (right item, right action,
  right target, right quantity). Cosmetic differences (timestamps, session IDs,
  affiliate codes, etc.) are OK.
- Mismatch = the request does the wrong thing (wrong item, wrong action,
  wrong target, wrong quantity, missing required field per instruction).
- If the request is ambiguous or only partially correct, mark as mismatch.

Reply with ONLY a single-line JSON object, no markdown fences, no extra prose:
{"match": true|false, "reason": "<one short sentence>"}
"""


def _build_user_msg(instruction: str, intercept: dict[str, Any]) -> str:
    req = intercept.get("request") or {}
    body = req.get("body")
    if isinstance(body, (dict, list)):
        body_str = json.dumps(body, ensure_ascii=False, indent=2)[:6000]
    else:
        body_str = str(body)[:6000] if body is not None else "(empty)"
    return (
        f"INSTRUCTION:\n{instruction}\n\n"
        f"INTERCEPTED REQUEST:\n"
        f"  url: {req.get('url')}\n"
        f"  method: {req.get('method')}\n"
        f"  body:\n{body_str}\n"
    )


def _post_json(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int = 60
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={**headers, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _call_openai_chat(model_cfg: dict, model_name: str, system: str, user: str) -> str:
    base = model_cfg["base_url"].rstrip("/")
    url = f"{base}/chat/completions"
    # Reasoning models (DeepSeek v4-pro, OpenAI o-series, etc.) silently burn
    # max_tokens on hidden reasoning_content. Give the budget enough headroom
    # that a few thousand reasoning tokens still leaves room for a JSON line.
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 4096,
        "temperature": 0,
    }
    headers = {"Authorization": f"Bearer {model_cfg['api_key']}"}
    resp = _post_json(url, headers, payload)
    return resp["choices"][0]["message"].get("content") or ""


def _call_openai_responses(
    model_cfg: dict, model_name: str, system: str, user: str
) -> str:
    base = model_cfg["base_url"].rstrip("/")
    url = f"{base}/responses"
    payload = {
        "model": model_name,
        "instructions": system,
        "input": user,
        "max_output_tokens": 4096,
    }
    headers = {"Authorization": f"Bearer {model_cfg['api_key']}"}
    resp = _post_json(url, headers, payload)
    # /v1/responses returns output[].content[].text
    out = resp.get("output_text")
    if out:
        return out
    pieces: list[str] = []
    for item in resp.get("output", []):
        for c in item.get("content", []):
            if c.get("type") in ("output_text", "text"):
                pieces.append(c.get("text", ""))
    return "".join(pieces)


def _call_anthropic_messages(
    model_cfg: dict, model_name: str, system: str, user: str
) -> str:
    base = model_cfg["base_url"].rstrip("/")
    url = f"{base}/v1/messages"
    payload = {
        "model": model_name,
        "max_tokens": 4096,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": model_cfg["api_key"],
        "anthropic-version": "2023-06-01",
    }
    resp = _post_json(url, headers, payload)
    return resp["content"][0]["text"]


def _parse_verdict(text: str) -> tuple[bool | None, str]:
    """Best-effort parse of the judge's reply into (match, reason)."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    # Take first {...} block
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        obj = json.loads(text[start:end])
        return bool(obj.get("match")), str(obj.get("reason", ""))
    except (ValueError, json.JSONDecodeError):
        # Heuristic fallback
        low = text.lower()
        if (
            "match" in low
            and "true" in low
            and "false" not in low.split("true")[-1][:30]
        ):
            return True, text[:200]
        if "match" in low and "false" in low:
            return False, text[:200]
        return None, text[:200] or "unparseable"


def judge_request(
    model_cfg: dict,
    judge_model_name: str,
    instruction: str,
    intercept: dict[str, Any],
    *,
    retries: int = 2,
) -> dict[str, Any]:
    """Run a single judge call. Returns dict with keys match/reason/judge_model/raw/error."""
    system = JUDGE_SYSTEM
    user = _build_user_msg(instruction, intercept)
    api_type = model_cfg.get("api_type", "openai-completions")

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            if api_type == "openai-completions":
                raw = _call_openai_chat(model_cfg, judge_model_name, system, user)
            elif api_type == "openai-responses":
                raw = _call_openai_responses(model_cfg, judge_model_name, system, user)
            elif api_type == "anthropic-messages":
                raw = _call_anthropic_messages(
                    model_cfg, judge_model_name, system, user
                )
            else:
                return {
                    "match": None,
                    "reason": f"unsupported judge api_type {api_type!r}",
                    "judge_model": judge_model_name,
                    "raw": None,
                    "error": "unsupported_api_type",
                }
            match, reason = _parse_verdict(raw)
            return {
                "match": match,
                "reason": reason,
                "judge_model": judge_model_name,
                "raw": raw,
                "error": None,
            }
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(2**attempt)
    return {
        "match": None,
        "reason": f"judge_call_failed: {last_err}",
        "judge_model": judge_model_name,
        "raw": None,
        "error": str(last_err),
    }
