"""Token and estimated-cost accounting for agent transcripts."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_CACHE_TTL_S = 300
_MODELS_CACHE: tuple[float, dict[str, dict[str, Any]]] | None = None


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


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _first_int(data: dict[str, Any], keys: Iterable[str]) -> int:
    for key in keys:
        value = _to_int(data.get(key))
        if value:
            return value
    return 0


def _normalize_usage(raw: dict[str, Any]) -> dict[str, int]:
    input_details = raw.get("input_tokens_details")
    output_details = raw.get("output_tokens_details")
    if not isinstance(input_details, dict):
        input_details = {}
    if not isinstance(output_details, dict):
        output_details = {}

    explicit_cache_read = _first_int(
        raw,
        (
            "cacheRead",
            "cache_read",
            "cache_read_tokens",
            "cache_read_input_tokens",
        ),
    )
    nested_cache_read = _first_int(
        input_details, ("cached_tokens", "cache_read_tokens")
    )

    usage = {
        "input_tokens": _first_int(
            raw,
            (
                "input",
                "prompt",
                "prompt_tokens",
                "input_tokens",
            ),
        ),
        "output_tokens": _first_int(
            raw,
            (
                "output",
                "completion",
                "completion_tokens",
                "output_tokens",
            ),
        ),
        "cache_read_tokens": explicit_cache_read or nested_cache_read,
        "cache_write_tokens": _first_int(
            raw,
            (
                "cacheWrite",
                "cache_write",
                "cache_write_tokens",
                "cache_creation_input_tokens",
            ),
        ),
        "reasoning_tokens": _first_int(
            raw,
            (
                "reasoning",
                "reasoning_tokens",
                "internal_reasoning",
                "internal_reasoning_tokens",
            ),
        )
        or _first_int(output_details, ("reasoning_tokens",)),
        "reported_total_tokens": _first_int(
            raw,
            (
                "totalTokens",
                "total_tokens",
                "total",
            ),
        ),
    }
    if nested_cache_read and not explicit_cache_read:
        usage["input_tokens"] = max(usage["input_tokens"] - nested_cache_read, 0)
    usage["total_tokens"] = (
        usage["input_tokens"]
        + usage["output_tokens"]
        + usage["cache_read_tokens"]
        + usage["cache_write_tokens"]
        + usage["reasoning_tokens"]
    ) or usage["reported_total_tokens"]
    return usage


def _merge_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "reasoning_tokens",
        "reported_total_tokens",
        "total_tokens",
    ):
        total[key] += usage.get(key, 0)


def fetch_openrouter_pricing(
    *,
    base_url: str | None = None,
    timeout: float = 3.0,
) -> dict[str, dict[str, Any]]:
    """Fetch OpenRouter model pricing, returning an id -> model map."""
    global _MODELS_CACHE
    now = time.time()
    if _MODELS_CACHE and now - _MODELS_CACHE[0] < _CACHE_TTL_S:
        return _MODELS_CACHE[1]

    url = OPENROUTER_MODELS_URL
    if base_url and "openrouter.ai" in base_url:
        url = base_url.rstrip("/") + "/models"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "clawbench/usage"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        json.JSONDecodeError,
    ):
        return {}

    models: dict[str, dict[str, Any]] = {}
    for row in payload.get("data", []):
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            models[row["id"]] = row
    _MODELS_CACHE = (now, models)
    return models


def resolve_openrouter_model(
    candidates: Iterable[str],
    models: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Resolve model aliases against OpenRouter model ids."""
    normalized = [c.strip() for c in candidates if c and c.strip()]
    for candidate in normalized:
        if candidate in models:
            return models[candidate]
    for candidate in normalized:
        suffix = f"/{candidate}"
        matches = [row for model_id, row in models.items() if model_id.endswith(suffix)]
        if len(matches) == 1:
            return matches[0]
    return None


def _pricing_rates(model_row: dict[str, Any] | None) -> dict[str, Decimal | None]:
    pricing = model_row.get("pricing") if isinstance(model_row, dict) else None
    if not isinstance(pricing, dict):
        pricing = {}
    return {
        "input_tokens": _to_decimal(pricing.get("prompt")),
        "output_tokens": _to_decimal(pricing.get("completion")),
        "cache_read_tokens": _to_decimal(pricing.get("input_cache_read")),
        "cache_write_tokens": _to_decimal(pricing.get("input_cache_write")),
        "reasoning_tokens": _to_decimal(pricing.get("internal_reasoning")),
    }


def _estimate_cost_usd(
    totals: dict[str, int],
    model_row: dict[str, Any] | None,
) -> tuple[float | None, list[str]]:
    rates = _pricing_rates(model_row)
    if rates["input_tokens"] is None and rates["output_tokens"] is None:
        return None, []

    missing: list[str] = []
    cost = Decimal("0")
    for key, rate in rates.items():
        tokens = totals.get(key, 0)
        if not tokens:
            continue
        if rate is None:
            missing.append(key)
            continue
        cost += Decimal(tokens) * rate
    return float(cost), missing


def _event_usage_key(event: dict[str, Any], usage_owner: dict[str, Any]) -> str | None:
    message_id = usage_owner.get("id")
    if message_id:
        return f"message:{message_id}"
    response_id = usage_owner.get("responseId") or usage_owner.get("response_id")
    if response_id:
        return f"response:{response_id}"
    event_id = event.get("id")
    if event_id:
        return f"event:{event_id}"
    uuid = event.get("uuid")
    if uuid:
        return f"uuid:{uuid}"
    timestamp = usage_owner.get("timestamp") or event.get("timestamp")
    model = usage_owner.get("model")
    if timestamp and model:
        return f"{model}:{timestamp}"
    return None


def _extract_usage_events(
    lines: Iterable[str],
) -> tuple[dict[str, int], int, set[str], int]:
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "reported_total_tokens": 0,
        "total_tokens": 0,
    }
    seen_keys: set[str] = set()
    observed_models: set[str] = set()
    api_calls = 0
    session_aggregate: dict[str, int] | None = None
    session_api_calls: int | None = None

    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        for key in ("model", "model_id", "modelId"):
            value = event.get(key)
            if isinstance(value, str) and value:
                observed_models.add(value.removeprefix("openrouter/"))

        if event.get("type") == "session_meta":
            for key in ("model", "model_id"):
                value = event.get(key)
                if isinstance(value, str) and value:
                    observed_models.add(value.removeprefix("openrouter/"))
            normalized = _normalize_usage(event)
            if normalized["total_tokens"]:
                session_aggregate = normalized
            if isinstance(event.get("api_call_count"), int):
                session_api_calls = event["api_call_count"]
            continue

        usage_owner: dict[str, Any] | None = None
        raw_usage = event.get("usage")
        if isinstance(raw_usage, dict):
            usage_owner = event
        else:
            message = event.get("message")
            if isinstance(message, dict):
                for key in ("model", "model_id", "modelId"):
                    value = message.get(key)
                    if isinstance(value, str) and value:
                        observed_models.add(value.removeprefix("openrouter/"))
                raw_usage = message.get("usage")
                if isinstance(raw_usage, dict):
                    usage_owner = message

        if not isinstance(raw_usage, dict) or usage_owner is None:
            continue

        usage_key = _event_usage_key(event, usage_owner)
        if usage_key and usage_key in seen_keys:
            continue
        if usage_key:
            seen_keys.add(usage_key)

        normalized = _normalize_usage(raw_usage)
        if normalized["total_tokens"]:
            api_calls += 1
            _merge_usage(totals, normalized)

    if session_aggregate is not None:
        totals = session_aggregate
        if session_api_calls is not None:
            api_calls = session_api_calls
        elif api_calls == 0:
            api_calls = 1
    elif session_api_calls is not None and api_calls == 0:
        api_calls = session_api_calls

    if totals["total_tokens"] == 0:
        totals["total_tokens"] = (
            totals["input_tokens"]
            + totals["output_tokens"]
            + totals["cache_read_tokens"]
            + totals["cache_write_tokens"]
            + totals["reasoning_tokens"]
        ) or totals["reported_total_tokens"]

    return totals, api_calls, observed_models, len(seen_keys)


def summarize_usage_lines(
    lines: Iterable[str],
    *,
    model_cfg: dict[str, Any] | None = None,
    pricing_models: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    totals, api_calls, observed_models, usage_events = _extract_usage_events(lines)
    configured_model = str(model_cfg.get("model", "")) if model_cfg else ""
    base_url = str(model_cfg.get("base_url", "")) if model_cfg else ""
    candidates = [configured_model, *sorted(observed_models)]

    models = pricing_models
    if models is None and "openrouter.ai" in base_url:
        models = fetch_openrouter_pricing(base_url=base_url or None)
    models = models or {}
    model_row = resolve_openrouter_model(candidates, models)
    cost, missing_rates = _estimate_cost_usd(totals, model_row)
    if totals["total_tokens"] == 0:
        cost = None

    if totals["total_tokens"] == 0 and api_calls == 0:
        status = "usage_unavailable"
    elif cost is None:
        status = "price_unavailable"
    else:
        status = "estimated"

    return {
        "status": status,
        "api_calls": api_calls,
        "usage_events": usage_events,
        "input_tokens": totals["input_tokens"],
        "output_tokens": totals["output_tokens"],
        "cache_read_tokens": totals["cache_read_tokens"],
        "cache_write_tokens": totals["cache_write_tokens"],
        "reasoning_tokens": totals["reasoning_tokens"],
        "total_tokens": totals["total_tokens"],
        "estimated_cost_usd": round(cost, 6) if cost is not None else None,
        "pricing_source_url": OPENROUTER_MODELS_URL,
        "matched_openrouter_model_id": (
            model_row.get("id") if isinstance(model_row, dict) else None
        ),
        "pricing_missing_components": missing_rates,
        "observed_models": sorted(observed_models),
    }


def summarize_usage_file(
    path: Path,
    *,
    model_cfg: dict[str, Any] | None = None,
    pricing_models: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            return summarize_usage_lines(
                f,
                model_cfg=model_cfg,
                pricing_models=pricing_models,
            )
    except OSError:
        return summarize_usage_lines(
            (),
            model_cfg=model_cfg,
            pricing_models=pricing_models,
        )


def summarize_usage_text(
    text: str,
    *,
    model_cfg: dict[str, Any] | None = None,
    pricing_models: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return summarize_usage_lines(
        text.splitlines(),
        model_cfg=model_cfg,
        pricing_models=pricing_models,
    )


def format_usage_status(summary: dict[str, Any]) -> str:
    total = _to_int(summary.get("total_tokens"))
    if total <= 0:
        return "tokens pending"
    calls = _to_int(summary.get("api_calls"))
    call_part = f"{calls} calls" if calls else "calls pending"
    cost = summary.get("estimated_cost_usd")
    if isinstance(cost, (int, float)):
        cost_part = f"${cost:.4f}"
    elif summary.get("status") == "price_unavailable":
        cost_part = "price unavailable"
    else:
        cost_part = "cost pending"
    return f"{call_part}  •  {total:,} tok  •  {cost_part}"


def format_usage_summary(summary: dict[str, Any]) -> str:
    total = _to_int(summary.get("total_tokens"))
    if total <= 0:
        return "Usage: unavailable"
    parts = [
        f"{total:,} total",
        f"{_to_int(summary.get('input_tokens')):,} input",
        f"{_to_int(summary.get('output_tokens')):,} output",
    ]
    cache_read = _to_int(summary.get("cache_read_tokens"))
    cache_write = _to_int(summary.get("cache_write_tokens"))
    reasoning = _to_int(summary.get("reasoning_tokens"))
    if cache_read:
        parts.append(f"{cache_read:,} cache read")
    if cache_write:
        parts.append(f"{cache_write:,} cache write")
    if reasoning:
        parts.append(f"{reasoning:,} reasoning")

    cost = summary.get("estimated_cost_usd")
    if isinstance(cost, (int, float)):
        cost_part = f"estimated cost ${cost:.6f}"
    elif summary.get("status") == "price_unavailable":
        cost_part = "price unavailable"
    else:
        cost_part = "cost unavailable"
    model = summary.get("matched_openrouter_model_id") or "unmatched model"
    return f"Usage: {', '.join(parts)}; {cost_part} ({summary.get('status')}, {model})"
