#!/usr/bin/env python3
"""browser-use harness LiteLLM usage logger."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from litellm.integrations.custom_logger import CustomLogger

OUT = Path("/data/usage.jsonl")


def _to_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(float(value)), 0)
        except ValueError:
            return 0
    return 0


def _usage_dict(response_obj: Any) -> dict[str, Any]:
    if isinstance(response_obj, dict):
        usage = response_obj.get("usage") or response_obj.get("token_usage")
        return usage if isinstance(usage, dict) else {}
    usage = getattr(response_obj, "usage", None)
    if isinstance(usage, dict):
        return usage
    try:
        model_dump = response_obj.model_dump()
    except Exception:
        return {}
    usage = model_dump.get("usage") or model_dump.get("token_usage")
    return usage if isinstance(usage, dict) else {}


def _hidden_params(response_obj: Any) -> dict[str, Any]:
    if isinstance(response_obj, dict):
        hidden = response_obj.get("_hidden_params")
    else:
        hidden = getattr(response_obj, "_hidden_params", None)
    return hidden if isinstance(hidden, dict) else {}


def _row(kwargs: dict[str, Any], response_obj: Any) -> dict[str, Any] | None:
    usage = _usage_dict(response_obj)
    prompt = _to_int(usage.get("prompt_tokens") or usage.get("input_tokens"))
    completion = _to_int(usage.get("completion_tokens") or usage.get("output_tokens"))
    cache_read = _to_int(
        usage.get("cache_read_tokens") or usage.get("cache_read_input_tokens")
    )
    cache_write = _to_int(
        usage.get("cache_write_tokens") or usage.get("cache_creation_input_tokens")
    )
    reasoning = _to_int(
        usage.get("reasoning_tokens") or usage.get("internal_reasoning_tokens")
    )
    total = (prompt + completion + cache_read + cache_write + reasoning) or _to_int(
        usage.get("total_tokens") or usage.get("totalTokens")
    )
    if total <= 0:
        return None
    model = str(kwargs.get("model") or getattr(response_obj, "model", "") or "")
    hidden = _hidden_params(response_obj)
    response_cost = hidden.get("response_cost")
    cost = response_cost if isinstance(response_cost, (int, float)) else None
    matched_model = hidden.get("model_id") or hidden.get("custom_llm_provider")
    response_id = (
        getattr(response_obj, "id", None)
        or (response_obj.get("id") if isinstance(response_obj, dict) else None)
        or f"browser-use:{model}:{time.time()}"
    )
    return {
        "type": "usage",
        "source_harness": "browser-use",
        "call_id": f"response:{response_id}",
        "timestamp": time.time(),
        "model": model,
        "input_tokens": prompt,
        "output_tokens": completion,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "reasoning_tokens": reasoning,
        "total_tokens": total,
        "estimated_cost_usd": round(cost, 6) if cost is not None else None,
        "cost_status": "estimated" if cost is not None else "price_unavailable",
        "pricing_source_url": "https://openrouter.ai/api/v1/models",
        "matched_model_id": str(matched_model) if matched_model else None,
    }


class BrowserUseUsageLogger(CustomLogger):
    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        row = _row(kwargs, response_obj)
        if row is None:
            return
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


proxy_handler_instance = BrowserUseUsageLogger()
