#!/usr/bin/env python3
"""Pi harness LiteLLM usage logger."""

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


class PiUsageLogger(CustomLogger):
    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        if isinstance(response_obj, dict):
            usage = response_obj.get("usage") or {}
            response_id = response_obj.get("id")
            model = response_obj.get("model") or kwargs.get("model") or ""
            hidden = response_obj.get("_hidden_params")
        else:
            usage = getattr(response_obj, "usage", None) or {}
            response_id = getattr(response_obj, "id", None)
            model = getattr(response_obj, "model", None) or kwargs.get("model") or ""
            hidden = getattr(response_obj, "_hidden_params", None)
        if not isinstance(usage, dict):
            return
        prompt = _to_int(usage.get("prompt_tokens") or usage.get("input_tokens"))
        completion = _to_int(
            usage.get("completion_tokens") or usage.get("output_tokens")
        )
        cache_read = _to_int(
            usage.get("cache_read_tokens") or usage.get("cache_read_input_tokens")
        )
        cache_write = _to_int(
            usage.get("cache_write_tokens") or usage.get("cache_creation_input_tokens")
        )
        reasoning = _to_int(
            usage.get("reasoning_tokens") or usage.get("internal_reasoning_tokens")
        )
        total = prompt + completion + cache_read + cache_write + reasoning
        total = total or _to_int(usage.get("total_tokens") or usage.get("totalTokens"))
        if total <= 0:
            return
        hidden = hidden if isinstance(hidden, dict) else {}
        response_cost = hidden.get("response_cost")
        cost = response_cost if isinstance(response_cost, (int, float)) else None
        matched_model = hidden.get("model_id") or hidden.get("custom_llm_provider")
        row = {
            "type": "usage",
            "source_harness": "pi",
            "call_id": f"response:{response_id or time.time()}",
            "timestamp": time.time(),
            "model": str(model),
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
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


proxy_handler_instance = PiUsageLogger()
