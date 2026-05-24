"""ClawBench browser-use agent driver.

Talks to the local LiteLLM proxy (localhost:4000) via browser-use's
ChatOpenAI wrapper.
Streams transcript to /data/agent-messages.jsonl after every step so
partial history survives a watchdog kill.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from browser_use import Agent, Browser, ChatOpenAI, Tools

OUT = Path("/data/agent-messages.jsonl")
USAGE_OUT = Path("/data/usage.jsonl")
STOP = Path("/data/.stop-requested")  # extension-server eval-match marker

# Map our THINKING_LEVEL values onto browser-use's `reasoning_effort` levels.
_EFFORT_MAP = {
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "adaptive": "medium",
    "high": "high",
    "xhigh": "high",
}
_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_PRICING: dict[str, dict[str, Any]] | None = None
_USAGE_CALLS = 0


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


def _pricing_models() -> dict[str, dict[str, Any]]:
    global _PRICING
    if _PRICING is not None:
        return _PRICING
    base_url = os.environ.get("BU_UPSTREAM_BASE_URL", "")
    if "openrouter.ai" not in base_url:
        _PRICING = {}
        return _PRICING
    try:
        req = urllib.request.Request(
            base_url.rstrip("/") + "/models",
            headers={"User-Agent": "clawbench/browser-use-usage"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        _PRICING = {}
        return _PRICING
    _PRICING = {
        row["id"]: row
        for row in payload.get("data", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    return _PRICING


def _matched_model(model: str) -> dict[str, Any] | None:
    models = _pricing_models()
    candidates = [
        os.environ.get("BU_UPSTREAM_MODEL_ID", ""),
        model,
        model.removeprefix("openrouter/"),
    ]
    for candidate in candidates:
        if candidate in models:
            return models[candidate]
    for candidate in candidates:
        suffix = f"/{candidate}"
        matches = [row for key, row in models.items() if key.endswith(suffix)]
        if len(matches) == 1:
            return matches[0]
    return None


def _estimate_cost(
    row: dict[str, Any], model_row: dict[str, Any] | None
) -> float | None:
    pricing = model_row.get("pricing") if isinstance(model_row, dict) else None
    if not isinstance(pricing, dict):
        return None
    rates = {
        "input_tokens": _to_decimal(pricing.get("prompt")),
        "output_tokens": _to_decimal(pricing.get("completion")),
        "cache_read_tokens": _to_decimal(pricing.get("input_cache_read")),
        "cache_write_tokens": _to_decimal(pricing.get("input_cache_write")),
    }
    if rates["input_tokens"] is None and rates["output_tokens"] is None:
        return None
    cost = Decimal("0")
    for key, rate in rates.items():
        tokens = _to_int(row.get(key))
        if not tokens:
            continue
        if rate is None:
            return None
        cost += Decimal(tokens) * rate
    return float(cost)


def _emit_usage(completion: Any, model: str) -> None:
    usage = getattr(completion, "usage", None)
    if usage is None:
        return
    raw = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
    cache_read = _to_int(raw.get("prompt_cached_tokens"))
    cache_write = _to_int(raw.get("prompt_cache_creation_tokens"))
    input_tokens = max(
        _to_int(raw.get("prompt_tokens")) - cache_read - cache_write,
        0,
    )
    row = {
        "type": "usage",
        "source_harness": "browser-use",
        "call_id": "",
        "timestamp": time.time(),
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": _to_int(raw.get("completion_tokens")),
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "reasoning_tokens": 0,
        "total_tokens": _to_int(raw.get("total_tokens")),
    }
    if not row["total_tokens"]:
        row["total_tokens"] = (
            row["input_tokens"]
            + row["output_tokens"]
            + row["cache_read_tokens"]
            + row["cache_write_tokens"]
        )
    if not row["total_tokens"]:
        return
    global _USAGE_CALLS
    _USAGE_CALLS += 1
    row["call_id"] = f"browser-use:{model}:{_USAGE_CALLS}:{row['timestamp']}"
    model_row = _matched_model(model)
    cost = _estimate_cost(row, model_row)
    row["estimated_cost_usd"] = round(cost, 6) if cost is not None else None
    row["cost_status"] = "estimated" if cost is not None else "price_unavailable"
    row["pricing_source_url"] = _OPENROUTER_MODELS_URL
    row["matched_model_id"] = (
        model_row.get("id") if isinstance(model_row, dict) else None
    )
    USAGE_OUT.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


class UsageTrackingChatOpenAI(ChatOpenAI):
    async def ainvoke(self, messages, output_format=None, **kwargs):
        completion = await super().ainvoke(
            messages,
            output_format=output_format,
            **kwargs,
        )
        _emit_usage(completion, self.model)
        return completion


def make_llm() -> ChatOpenAI:
    """Construct browser-use's ChatOpenAI pointed at the local LiteLLM proxy."""
    model = os.environ["BU_MODEL_NAME"]
    base_url = os.environ["BU_BASE_URL"]
    api_key = os.environ["BU_API_KEY"]
    temperature = float(os.environ.get("BU_TEMPERATURE", "0.0"))
    thinking = os.environ.get("BU_THINKING_LEVEL", "off").lower()
    effort = _EFFORT_MAP.get(thinking) if thinking != "off" else None

    kw: dict[str, Any] = {
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "temperature": temperature,
    }
    if effort:
        kw["reasoning_effort"] = effort
        kw["reasoning_models"] = [model]
    return UsageTrackingChatOpenAI(**kw)


def dump_history(agent_obj) -> None:
    """Write the current AgentHistoryList to /data/agent-messages.jsonl as JSONL."""
    with OUT.open("w") as f:
        for h in agent_obj.history.history:
            f.write(json.dumps(h.model_dump(), default=str, ensure_ascii=False) + "\n")


async def main() -> None:
    instruction = os.environ["INSTRUCTION"]
    time_limit = int(os.environ.get("TIME_LIMIT_S", "1800"))
    thinking = os.environ.get("BU_THINKING_LEVEL", "off").lower()

    # Discover any files mounted under /root/workspace/my-info/ so the
    # agent's read_file tool can access them. browser-use's FileSystem
    # only exposes paths listed in `available_file_paths`; without this
    # the model sees "file not found" for every credential lookup.
    workspace = Path("/root/workspace")
    my_info = workspace / "my-info"
    available_files: list[str] = []
    if my_info.exists():
        for p in my_info.rglob("*"):
            if p.is_file():
                available_files.append(str(p))

    llm = make_llm()
    browser = Browser(cdp_url="http://127.0.0.1:9222")
    tools = Tools()  # default: browser-only actions, no shell escape

    OUT.write_text("")  # truncate

    # We need access to the full agent for `agent.history`, so we close
    # over a mutable holder populated after Agent() is constructed.
    holder: dict = {}

    async def on_step(_state, _output, _step_num):
        agent_obj = holder.get("agent")
        if agent_obj is not None:
            dump_history(agent_obj)

    async def should_stop() -> bool:
        # Cooperate with the harness watchdog when the eval interceptor
        # signals a match by touching /data/.stop-requested.
        return STOP.exists()

    async def on_done(_history):
        agent_obj = holder.get("agent")
        if agent_obj is not None:
            dump_history(agent_obj)

    agent = Agent(
        task=instruction,
        llm=llm,
        browser=browser,
        tools=tools,
        use_vision=True,
        use_thinking=(thinking != "off"),
        file_system_path=str(workspace),
        available_file_paths=available_files,
        register_new_step_callback=on_step,
        register_done_callback=on_done,
        register_should_stop_callback=should_stop,
    )
    holder["agent"] = agent

    try:
        await asyncio.wait_for(agent.run(), timeout=time_limit)
    except asyncio.TimeoutError:
        # The harness watchdog will set the stop-reason; we just need to
        # land the most-recent transcript.
        pass
    finally:
        # Final dump in case the last step's callback didn't get to fire.
        try:
            dump_history(agent)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
