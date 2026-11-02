#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

try:
    from clawbench.runtime.harbor.body import RenderedBody, render_body
except ModuleNotFoundError:
    # The Harbor image copies this directory to /app/src/harbor and runs this
    # file directly, so the installed clawbench package is not available there.
    from body import RenderedBody, render_body

JUDGE_SYSTEM_STRICT = """You are a strict evaluator for a web-agent benchmark.

A user gave a natural-language INSTRUCTION to an autonomous browser agent.
The agent navigated a real website and finally produced a single HTTP request
(URL + method + body) that we INTERCEPTED before it was sent to the server.

Decide whether this intercepted request, if it had been sent, would correctly
fulfill the user's instruction.

Rules:
- Match = the request would do what the user asked (right item, right action,
  right target, right quantity). Cosmetic differences are OK.
- Mismatch = wrong item, wrong action, wrong target, wrong quantity, or missing
  required field per instruction.
- If the request is ambiguous or only partially correct, mark as mismatch.

Reply with ONLY a single-line JSON object:
{"match": true|false, "reason": "<one short sentence>"}
"""

JUDGE_SYSTEM_LENIENT = """You are a lenient evaluator for a web-agent benchmark.

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


def write_reward(
    reward: float, payload: dict[str, Any], output_dir: Path = Path("/logs/verifier")
) -> None:
    out = output_dir
    out.mkdir(parents=True, exist_ok=True)
    result = {"reward": reward, **payload}
    metrics = {
        "reward": reward,
        "intercepted": float(bool(payload.get("intercepted"))),
    }
    for name in (
        "reward_lenient",
        "reward_strict",
        "judge_match",
        "judge_match_lenient",
        "judge_match_strict",
        "body_truncated",
        "body_length",
    ):
        value = payload.get(name)
        if isinstance(value, (bool, int, float)):
            metrics[name] = float(value)

    (out / "reward.txt").write_text(str(reward))
    (out / "reward.json").write_text(json.dumps(metrics, indent=2))
    (out / "clawbench-result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )


def post_json(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int = 60
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={**headers, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def build_user_msg(
    instruction: str,
    intercept: dict[str, Any],
    judge_context: dict[str, Any] | None,
    rendered_body: RenderedBody | None = None,
) -> str:
    req = intercept.get("request") or {}
    body_text = (rendered_body or render_body(req.get("body"))).prompt_text()
    context = ""
    if isinstance(judge_context, dict):
        pieces = []
        for key in ("rubric", "reference_solution", "source_task_yaml"):
            value = judge_context.get(key)
            if isinstance(value, str) and value.strip():
                pieces.append(f"{key}:\n{value.strip()[:6000]}")
        if pieces:
            context = "\n\nHIDDEN JUDGE CONTEXT:\n" + "\n\n".join(pieces)
    return (
        f"INSTRUCTION:\n{instruction}\n\n"
        "INTERCEPTED REQUEST:\n"
        f"  url: {req.get('url')}\n"
        f"  method: {req.get('method')}\n"
        f"  body:\n{body_text}\n"
        f"{context}\n"
    )


def parse_verdict(text: str) -> tuple[bool | None, str]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        obj = json.loads(text[start:end])
        match = obj.get("match")
        return (match if isinstance(match, bool) else None), str(obj.get("reason", ""))
    except (ValueError, json.JSONDecodeError):
        return None, text[:200] or "unparseable judge response"


def call_judge(
    model_cfg: dict[str, str],
    instruction: str,
    intercept: dict[str, Any],
    judge_context: dict[str, Any] | None,
    system_prompt: str,
    max_tokens: int,
) -> dict[str, Any]:
    api_type = model_cfg["api_type"]
    model = model_cfg["model"]
    base_url = model_cfg["base_url"].rstrip("/")
    req = intercept.get("request") or {}
    rendered_body = render_body(req.get("body"))
    user = build_user_msg(instruction, intercept, judge_context, rendered_body)
    if api_type == "openai-completions":
        resp = post_json(
            f"{base_url}/chat/completions",
            {"Authorization": f"Bearer {model_cfg['api_key']}"},
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user},
                ],
                "max_tokens": max_tokens,
                "temperature": 0,
            },
        )
        raw = resp["choices"][0]["message"].get("content") or ""
    elif api_type == "openai-responses":
        resp = post_json(
            f"{base_url}/responses",
            {"Authorization": f"Bearer {model_cfg['api_key']}"},
            {
                "model": model,
                "instructions": system_prompt,
                "input": user,
                "max_output_tokens": max_tokens,
            },
        )
        raw = resp.get("output_text") or ""
        if not raw:
            raw = "".join(
                c.get("text", "")
                for item in resp.get("output", [])
                for c in item.get("content", [])
                if c.get("type") in ("output_text", "text")
            )
    elif api_type == "anthropic-messages":
        resp = post_json(
            f"{base_url}/v1/messages",
            {
                "x-api-key": model_cfg["api_key"],
                "anthropic-version": "2023-06-01",
            },
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user}],
            },
        )
        raw = resp["content"][0]["text"]
    else:
        verdict = {
            "match": None,
            "reason": f"unsupported judge api_type {api_type!r}",
            "raw": None,
            "error": "unsupported_api_type",
        }
        verdict.update(rendered_body.verdict_metadata())
        return verdict
    match, reason = parse_verdict(raw)
    if (
        rendered_body.truncated
        and system_prompt == JUDGE_SYSTEM_LENIENT
        and match is True
    ):
        match = False
        reason = (
            "body was truncated; a positive lenient match requires the complete body"
        )
    verdict = {"match": match, "reason": reason, "raw": raw, "error": None}
    verdict.update(rendered_body.verdict_metadata())
    return verdict


def call_judge_with_retries(
    model_cfg: dict[str, str],
    instruction: str,
    intercept: dict[str, Any],
    judge_context: dict[str, Any] | None,
    system_prompt: str,
    max_tokens: int,
) -> dict[str, Any]:
    last_error = ""
    for attempt in range(3):
        try:
            return call_judge(
                model_cfg,
                instruction,
                intercept,
                judge_context,
                system_prompt,
                max_tokens,
            )
        except Exception as exc:
            last_error = str(exc)
            if attempt < 2:
                time.sleep(2**attempt)
    return {
        "match": None,
        "reason": f"judge_call_failed: {last_error}",
        "raw": None,
        "error": last_error,
        **render_body((intercept.get("request") or {}).get("body")).verdict_metadata(),
    }


def main() -> int:
    task_path = Path("/tests/task.json")
    intercept_path = Path("/data/interception.json")
    task_id = None
    task = {}
    if task_path.exists():
        task = json.loads(task_path.read_text())
        metadata = (
            task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        )
        task_id = metadata.get("task_id")

    if not intercept_path.exists():
        write_reward(
            0.0,
            {
                "reward_lenient": 0.0,
                "reward_strict": 0.0,
                "intercepted": False,
                "judge_match": None,
                "judge_match_lenient": None,
                "judge_match_strict": None,
                "reason": "missing /data/interception.json",
                "task_id": task_id,
            },
        )
        return 0

    intercept = json.loads(intercept_path.read_text())
    if not intercept.get("intercepted"):
        write_reward(
            0.0,
            {
                "reward_lenient": 0.0,
                "reward_strict": 0.0,
                "intercepted": False,
                "judge_match": None,
                "judge_match_lenient": None,
                "judge_match_strict": None,
                "reason": intercept.get("stop_description")
                or intercept.get("stop_reason")
                or "not intercepted",
                "task_id": task_id,
            },
        )
        return 0

    cfg = {
        "base_url": os.environ.get("CLAWBENCH_JUDGE_BASE_URL", ""),
        "api_key": os.environ.get("CLAWBENCH_JUDGE_API_KEY", ""),
        "model": os.environ.get("CLAWBENCH_JUDGE_MODEL", "deepseek-v4-pro"),
        "api_type": os.environ.get("CLAWBENCH_JUDGE_API_TYPE", "openai-completions"),
    }
    if not cfg["base_url"] or not cfg["api_key"]:
        write_reward(
            0.0,
            {
                "reward_lenient": 0.0,
                "reward_strict": 0.0,
                "intercepted": True,
                "judge_match": None,
                "judge_match_lenient": None,
                "judge_match_strict": None,
                "reason": "missing judge configuration",
                "task_id": task_id,
                **render_body(
                    (intercept.get("request") or {}).get("body")
                ).verdict_metadata(),
            },
        )
        return 0

    instruction = str(task.get("instruction") or "")
    judge_context = (
        task.get("judge_context")
        if isinstance(task.get("judge_context"), dict)
        else None
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        lenient_future = executor.submit(
            call_judge_with_retries,
            cfg,
            instruction,
            intercept,
            None,
            JUDGE_SYSTEM_LENIENT,
            800,
        )
        strict_future = executor.submit(
            call_judge_with_retries,
            cfg,
            instruction,
            intercept,
            judge_context,
            JUDGE_SYSTEM_STRICT,
            4096,
        )
        lenient_result = lenient_future.result()
        strict_result = strict_future.result()

    match_lenient = lenient_result.get("match")
    match_strict = strict_result.get("match")
    reward_lenient = 1.0 if match_lenient is True else 0.0
    reward_strict = 1.0 if match_strict is True else 0.0
    write_reward(
        reward_lenient,
        {
            "reward_lenient": reward_lenient,
            "reward_strict": reward_strict,
            "intercepted": True,
            "judge_match": match_lenient,
            "judge_match_lenient": match_lenient,
            "judge_match_strict": match_strict,
            "reason": {
                "lenient": lenient_result.get("reason")
                or lenient_result.get("error")
                or "",
                "strict": strict_result.get("reason")
                or strict_result.get("error")
                or "",
            },
            "judge_model": cfg["model"],
            "task_id": task_id,
            "body_truncated": lenient_result.get("body_truncated"),
            "body_length": lenient_result.get("body_length"),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
