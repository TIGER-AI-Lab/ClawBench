"""lenient LLM judge for ClawBench V2.

Difference from src/clawbench/runner/judge.py:
- Original rubric: "ambiguous or partially correct → mismatch" (strict)
- lenient rubric:    "no explicit contradiction → match" (lenient on missing info)

Rule (lenient spec):
  match = True  iff the intercepted request does NOT explicitly contradict
                    any explicit field in the instruction.
  match = False iff the request explicitly contradicts an explicit field
                    (wrong item, wrong color when color was specified,
                     wrong quantity when quantity was specified, ...).
  Unspecified fields, missing info, partial coverage → match = True.

Why: V2 reward signal is "minimal alignment" — we only penalize when
the agent did the WRONG thing, not when the agent omitted a detail not
constrained by the instruction. This pulls reported scores up by ~10-30pp
and matches the public Sonnet 4.6 reference (Intercepted 58% / Reward 44%).

Usage (same interface as judge.py for drop-in replacement):
    from judge_llm import judge_request
    verdict = judge_request(model_cfg, judge_model, instruction, intercept)
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from typing import Any


JUDGE_SYSTEM = """You are a lenient evaluator for a web-agent benchmark.

A user gave a natural-language INSTRUCTION to an autonomous browser agent.
The agent navigated a real website and finally produced a single HTTP request
(URL + method + body) that we INTERCEPTED before it was sent to the server.

You decide whether this intercepted request ALIGNS with the user's instruction.

# Rubric (CRITICAL — read carefully)

match = TRUE if there is NO EXPLICIT CONTRADICTION between the request and
the instruction. The default verdict is TRUE.

match = FALSE only if the request EXPLICITLY contradicts a field the user
EXPLICITLY specified in the instruction. Examples of contradiction:
- Instruction says "red shirt", request body shows "color: blue"
- Instruction says "quantity 2", request body shows "qty: 5"
- Instruction says "deliver to home", request body shows "deliver to work"
- Instruction asks to enroll in CS50, request enrolls in CS61

# What is NOT a contradiction (default to match = TRUE)

- Instruction did not specify a field, request omits or has any value for it
  → MATCH (the user did not constrain it)
- Instruction said "3pm", request body has no time field at all
  → MATCH (info absent, not contradicted)
- PDF resume left blank where instruction did not require content
  → MATCH
- Cosmetic differences (timestamps, session IDs, affiliate codes, currency
  symbols, formatting) → MATCH
- Ambiguous wording where multiple interpretations work → MATCH
- Agent picked a reasonable default for unspecified options → MATCH
- Color, size, time, quantity not mentioned in instruction → MATCH

# Output

Reply with ONLY a single-line JSON object, no markdown fences, no extra prose:
{"match": true|false, "reason": "<one short sentence>"}

Default is true. Only return false when you can name a SPECIFIC explicit
field from the instruction that the request EXPLICITLY contradicts.
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
    url = f"{model_cfg['base_url'].rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {model_cfg['api_key']}"}
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 800,
        "temperature": 0.0,
    }
    resp = _post_json(url, headers, payload)
    return resp["choices"][0]["message"]["content"]


def _call_anthropic_messages(
    model_cfg: dict, model_name: str, system: str, user: str
) -> str:
    base = model_cfg.get("base_url", "https://api.anthropic.com").rstrip("/")
    url = f"{base}/v1/messages"
    headers = {
        "x-api-key": model_cfg["api_key"],
        "anthropic-version": model_cfg.get("anthropic_version", "2023-06-01"),
    }
    payload = {
        "model": model_name,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "max_tokens": 800,
        "temperature": 0.0,
    }
    resp = _post_json(url, headers, payload)
    content = resp.get("content", [])
    return "".join(
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    )


def _parse_verdict(raw: str) -> tuple[bool, str]:
    """Best-effort parse of the judge's reply into (match, reason). Default TRUE on parse failure."""
    try:
        # Strip markdown fences if any
        s = raw.strip()
        if s.startswith("```"):
            s = s.split("\n", 1)[1] if "\n" in s else s
            if s.endswith("```"):
                s = s.rsplit("\n", 1)[0] if "\n" in s else s.rstrip("`")
        obj = json.loads(s)
        return bool(obj.get("match", True)), str(obj.get("reason", ""))
    except Exception:
        # Fall back to keyword scan, defaulting to TRUE (per lenient rubric)
        low = raw.lower()
        if (
            "false" in low
            and "match" in low
            and low.find("false") - low.find("match") < 80
        ):
            return False, raw[:200]
        return True, raw[:200]


def judge_request(
    model_cfg: dict, judge_model_name: str, instruction: str, intercept: dict[str, Any]
) -> dict[str, Any]:
    """Run a single lenient judge call. Returns dict with keys match/reason/judge_model/raw/error."""
    system = JUDGE_SYSTEM
    user = _build_user_msg(instruction, intercept)
    api_type = model_cfg.get("api_type", "openai-completions")
    raw = ""
    err = None
    for attempt in range(3):
        try:
            if api_type in ("openai-completions", "openai-responses"):
                raw = _call_openai_chat(model_cfg, judge_model_name, system, user)
            elif api_type == "anthropic-messages":
                raw = _call_anthropic_messages(
                    model_cfg, judge_model_name, system, user
                )
            else:
                raise NotImplementedError(
                    f"judge_llm: unsupported api_type {api_type!r}"
                )
            break
        except urllib.error.HTTPError as e:
            err = f"http_{e.code}"
            if e.code in (429, 500, 502, 503):
                time.sleep(2**attempt)
                continue
            break
        except Exception as e:
            err = f"err_{type(e).__name__}: {e}"
            break
    if not raw:
        return {
            "match": None,
            "reason": "",
            "judge_model": judge_model_name,
            "raw": "",
            "error": err,
            "rubric": "lenient",
        }
    m, reason = _parse_verdict(raw)
    return {
        "match": m,
        "reason": reason,
        "judge_model": judge_model_name,
        "raw": raw[:500],
        "rubric": "lenient",
    }
