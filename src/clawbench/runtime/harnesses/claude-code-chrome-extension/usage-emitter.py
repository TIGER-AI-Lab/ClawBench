#!/usr/bin/env python3
"""Harness-local usage emitter.

Each harness runs this inside its own container to translate that harness's
native transcript stream into /data/usage.jsonl. The host runner consumes only
the generated usage artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


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
    cache_details = raw.get("cache")
    if not isinstance(input_details, dict):
        input_details = {}
    if not isinstance(output_details, dict):
        output_details = {}
    if not isinstance(cache_details, dict):
        cache_details = {}

    explicit_cache_read = _first_int(
        raw,
        (
            "cacheRead",
            "cache_read",
            "cache_read_tokens",
            "cache_read_input_tokens",
        ),
    )
    nested_input_cache_read = _first_int(
        input_details,
        ("cached_tokens", "cache_read_tokens", "cache_read_input_tokens"),
    )
    nested_cache_read = nested_input_cache_read or _first_int(
        cache_details, ("read", "cache_read_tokens")
    )

    usage = {
        "input_tokens": _first_int(
            raw,
            ("input", "prompt", "prompt_tokens", "input_tokens"),
        ),
        "output_tokens": _first_int(
            raw,
            ("output", "completion", "completion_tokens", "output_tokens"),
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
        )
        or _first_int(cache_details, ("write", "cache_write_tokens")),
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
            ("totalTokens", "total_tokens", "total"),
        ),
    }
    if nested_input_cache_read and not explicit_cache_read:
        usage["input_tokens"] = max(
            usage["input_tokens"] - nested_input_cache_read,
            0,
        )
    usage["total_tokens"] = (
        usage["input_tokens"]
        + usage["output_tokens"]
        + usage["cache_read_tokens"]
        + usage["cache_write_tokens"]
        + usage["reasoning_tokens"]
    ) or usage["reported_total_tokens"]
    return usage


def _fetch_pricing(
    base_url: str | None, api_key: str | None
) -> dict[str, dict[str, Any]]:
    if not base_url or "openrouter.ai" not in base_url:
        return {}
    url = base_url.rstrip("/") + "/models"
    headers = {"User-Agent": "clawbench/usage-emitter"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return {}
    return {
        row["id"]: row
        for row in payload.get("data", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }


def _resolve_model(
    candidates: Iterable[str], models: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    normalized = [c.removeprefix("openrouter/").strip() for c in candidates if c]
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
    completion_rate = _to_decimal(pricing.get("completion"))
    return {
        "input_tokens": _to_decimal(pricing.get("prompt")),
        "output_tokens": completion_rate,
        "cache_read_tokens": _to_decimal(pricing.get("input_cache_read")),
        "cache_write_tokens": _to_decimal(pricing.get("input_cache_write")),
        "reasoning_tokens": _to_decimal(pricing.get("internal_reasoning"))
        or completion_rate,
    }


def _estimate(
    row: dict[str, Any], model_row: dict[str, Any] | None
) -> tuple[float | None, str]:
    rates = _pricing_rates(model_row)
    if rates["input_tokens"] is None and rates["output_tokens"] is None:
        return None, "price_unavailable"
    cost = Decimal("0")
    for key, rate in rates.items():
        tokens = _to_int(row.get(key))
        if not tokens:
            continue
        if rate is None:
            return None, "price_unavailable"
        cost += Decimal(tokens) * rate
    return float(cost), "estimated"


def _event_usage_key(event: dict[str, Any], owner: dict[str, Any]) -> str | None:
    for key in ("id", "message_id"):
        value = owner.get(key)
        if value:
            return f"message:{value}"
    response_id = owner.get("responseId") or owner.get("response_id")
    if response_id:
        return f"response:{response_id}"
    if event.get("id"):
        return f"event:{event['id']}"
    if event.get("uuid"):
        return f"uuid:{event['uuid']}"
    timestamp = owner.get("timestamp") or event.get("timestamp")
    model = owner.get("model") or event.get("model")
    if timestamp and model:
        return f"{model}:{timestamp}"
    return None


def _usage_candidates(
    event: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    raw_usage = event.get("usage")
    if isinstance(raw_usage, dict):
        candidates.append((raw_usage, event))

    message = event.get("message")
    if isinstance(message, dict):
        raw_usage = message.get("usage")
        if isinstance(raw_usage, dict):
            candidates.append((raw_usage, message))

    part = event.get("part")
    if isinstance(part, dict):
        for key in ("usage", "tokens"):
            raw_usage = part.get(key)
            if isinstance(raw_usage, dict):
                candidates.append((raw_usage, part))

    metadata = event.get("metadata")
    if isinstance(metadata, dict):
        for key in ("usage", "usage_metadata", "token_usage"):
            raw_usage = metadata.get(key)
            if isinstance(raw_usage, dict):
                candidates.append((raw_usage, metadata))

    response_metadata = event.get("response_metadata")
    if isinstance(response_metadata, dict):
        raw_usage = response_metadata.get("token_usage")
        if isinstance(raw_usage, dict):
            candidates.append((raw_usage, response_metadata))

    if event.get("type") == "session_meta":
        normalized = _normalize_usage(event)
        if normalized["total_tokens"]:
            candidates.append((event, event))
    return candidates


def _row_from_event(
    event: dict[str, Any],
    raw_usage: dict[str, Any],
    owner: dict[str, Any],
    *,
    harness: str,
    default_model: str,
    pricing_models: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    usage = _normalize_usage(raw_usage)
    if not usage["total_tokens"]:
        return None

    model = (
        owner.get("model")
        or owner.get("model_id")
        or owner.get("modelId")
        or event.get("model")
        or event.get("model_id")
        or event.get("modelId")
        or default_model
    )
    model = str(model).removeprefix("openrouter/") if model else default_model
    model_row = _resolve_model((model, default_model), pricing_models)
    cost, status = _estimate(usage, model_row)
    call_id = _event_usage_key(event, owner)
    if call_id is None:
        call_id = f"{harness}:{model}:{event.get('timestamp') or time.time()}"

    return {
        "type": "usage",
        "source_harness": harness,
        "call_id": call_id,
        "timestamp": owner.get("timestamp") or event.get("timestamp") or time.time(),
        "model": model,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cache_read_tokens": usage["cache_read_tokens"],
        "cache_write_tokens": usage["cache_write_tokens"],
        "reasoning_tokens": usage["reasoning_tokens"],
        "total_tokens": usage["total_tokens"],
        "estimated_cost_usd": round(cost, 6) if cost is not None else None,
        "cost_status": status,
        "pricing_source_url": OPENROUTER_MODELS_URL,
        "matched_model_id": (
            model_row.get("id") if isinstance(model_row, dict) else None
        ),
    }


def _load_seen(path: Path) -> set[str]:
    seen: set[str] = set()
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("call_id"):
                    seen.add(str(row["call_id"]))
    except OSError:
        pass
    return seen


def emit_once(args: argparse.Namespace, seen: set[str] | None = None) -> set[str]:
    seen = set(seen or ())
    pricing = getattr(args, "_pricing_models", None)
    if pricing is None:
        pricing = _fetch_pricing(args.base_url, args.api_key)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.output.exists():
        args.output.write_text("")
    try:
        lines = args.input.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return seen
    with args.output.open("a", encoding="utf-8") as out:
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            for raw_usage, owner in _usage_candidates(event):
                row = _row_from_event(
                    event,
                    raw_usage,
                    owner,
                    harness=args.harness,
                    default_model=args.model,
                    pricing_models=pricing,
                )
                if row is None:
                    continue
                call_id = str(row["call_id"])
                if call_id in seen:
                    continue
                seen.add(call_id)
                out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                out.write("\n")
                out.flush()
    return seen


def watch(args: argparse.Namespace) -> None:
    seen = _load_seen(args.output)
    args._pricing_models = _fetch_pricing(args.base_url, args.api_key)
    deadline = time.time() + args.max_seconds
    while time.time() < deadline:
        seen = emit_once(args, seen)
        time.sleep(args.interval)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("/data/usage.jsonl"))
    parser.add_argument("--model", default=os.environ.get("MODEL_NAME", ""))
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", ""))
    parser.add_argument("--api-key", default=os.environ.get("API_KEY", ""))
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=float(os.environ.get("TIME_LIMIT_S", "1800")) + 60,
    )
    args = parser.parse_args()
    if args.watch:
        watch(args)
    else:
        emit_once(args, _load_seen(args.output))


if __name__ == "__main__":
    main()
