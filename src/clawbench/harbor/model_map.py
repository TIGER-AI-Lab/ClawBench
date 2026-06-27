"""Single source of truth for ClawBench ↔ LiteLLM provider/model mapping.

Both Harbor directions rely on this module:

* The *harness* direction (``runtime/harnesses/harbor/harbor_driver.py``) maps a
  ClawBench model into the LiteLLM model id Terminus-2 hands to its backend.
* The *runner* direction (``clawbench.harbor.agent``) does the same so a Harbor
  ``provider/model`` string is faithfully translated into the
  ``MODEL_NAME``/``BASE_URL``/``API_TYPE`` env contract the ClawBench harnesses
  expect.

The mapping is intentionally stdlib-only (the harness driver runs inside a
minimal container venv) and pure: no network calls except the explicit,
best-effort OpenRouter model-id resolver, which callers opt into.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

# The LiteLLM/Harbor provider prefixes ClawBench knows how to emit.
LITELLM_PROVIDERS = ("openrouter", "anthropic", "gemini", "openai")

# ClawBench api_type values understood by the mapping.
CLAWBENCH_API_TYPES = (
    "openai-completions",
    "openai-responses",
    "anthropic-messages",
    "google-generative-ai",
)


@dataclass(frozen=True)
class LiteLLMModel:
    """Result of mapping a ClawBench model into LiteLLM terms.

    Attributes:
        model: The LiteLLM model id, e.g. ``gemini/gemini-3.5-flash``.
        api_base: Optional ``api_base`` override (``None`` = provider default).
        env: Provider credential env vars LiteLLM reads from the process.
        provider: The LiteLLM provider prefix (``gemini``/``openai``/...).
    """

    model: str
    api_base: str | None
    env: dict[str, str] = field(default_factory=dict)
    provider: str = ""


def pick_api_key(api_keys: list[str] | None = None, api_key: str | None = None) -> str:
    """Return a single API key from a list/single value.

    Mirrors the harness driver's ``_pick_api_key`` but as a pure function so the
    runner direction can reuse it. Harbor (LiteLLM) does not rotate keys, so the
    first key wins.
    """
    if api_keys:
        return api_keys[0]
    if api_key:
        return api_key
    raise ValueError("no API key provided (api_keys or api_key)")


def pick_api_key_from_env() -> str:
    """Pick an API key from the ClawBench container env (``API_KEYS``/``API_KEY``)."""
    keys_json = os.environ.get("API_KEYS", "")
    api_keys: list[str] | None = None
    if keys_json:
        try:
            parsed = json.loads(keys_json)
            if isinstance(parsed, list) and parsed:
                api_keys = [str(k) for k in parsed]
        except json.JSONDecodeError:
            api_keys = None
    return pick_api_key(api_keys, os.environ.get("API_KEY") or None)


def resolve_openrouter_model(base_url: str, model_name: str, key: str) -> str:
    """Best-effort resolve an OpenRouter canonical model id (e.g. ``x-ai/grok-4``).

    OpenRouter wants the provider-qualified id; falls back to the bare name on
    any error so callers never hard-fail on a transient network blip.
    """
    import urllib.request

    base_url = base_url.rstrip("/")
    try:
        req = urllib.request.Request(
            f"{base_url}/models", headers={"Authorization": f"Bearer {key}"}
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
        for m in resp.get("data", []):
            mid = m.get("id", "")
            if mid == model_name or mid.endswith(f"/{model_name}"):
                return mid
    except Exception:  # noqa: BLE001 - best effort, fall back to bare name
        pass
    return model_name


def build_litellm_model(
    base_url: str,
    model_name: str,
    api_type: str,
    key: str,
    *,
    resolve_openrouter: bool = True,
) -> LiteLLMModel:
    """Map ClawBench ``(base_url, model_name, api_type)`` to LiteLLM terms.

    Gemini note: a ``google-generative-ai`` model whose base_url is the
    OpenAI-compatible endpoint (``/v1beta/openai`` or any ``/openai`` base) is
    routed through LiteLLM's ``openai/<model>`` provider with ``api_base=base_url``
    so it POSTs ``/chat/completions`` (the path those keys are issued for). The
    native Google generative-language root (no ``/openai``) uses LiteLLM's
    ``gemini/<model>`` provider with ``GEMINI_API_KEY`` and ``api_base=None``.
    """
    base_url = base_url.rstrip("/")
    env: dict[str, str] = {}

    if "openrouter.ai" in base_url:
        resolved = (
            resolve_openrouter_model(base_url, model_name, key)
            if resolve_openrouter
            else model_name
        )
        env["OPENROUTER_API_KEY"] = key
        env["OPENROUTER_API_BASE"] = base_url
        return LiteLLMModel(f"openrouter/{resolved}", None, env, "openrouter")

    if api_type == "anthropic-messages":
        env["ANTHROPIC_API_KEY"] = key
        api_base = (
            None if base_url.startswith("https://api.anthropic.com") else base_url
        )
        return LiteLLMModel(f"anthropic/{model_name}", api_base, env, "anthropic")

    if api_type == "google-generative-ai":
        # An OpenAI-compatible Gemini endpoint (``/v1beta/openai`` or any ``/openai``
        # base) must route through LiteLLM's *openai* provider so the api_base is
        # preserved (POST ``/chat/completions``). LiteLLM's native ``gemini``
        # provider would drop the api_base and POST ``generateContent`` -- the
        # endpoint these OpenAI-compat keys are NOT issued for (silent auth failure
        # / 0 actions). This keeps the agent-path fix robust at the model_map layer.
        if "/v1beta/openai" in base_url or base_url.endswith("/openai"):
            env["OPENAI_API_KEY"] = key
            return LiteLLMModel(f"openai/{model_name}", base_url, env, "openai")
        env["GEMINI_API_KEY"] = key
        env["GOOGLE_API_KEY"] = key
        # Native Google root is the default for LiteLLM's gemini provider; only
        # override when a non-default (e.g. proxy) base_url is configured.
        api_base = (
            None
            if base_url.startswith("https://generativelanguage.googleapis.com")
            else base_url
        )
        return LiteLLMModel(f"gemini/{model_name}", api_base, env, "gemini")

    if api_type in ("openai-completions", "openai-responses"):
        env["OPENAI_API_KEY"] = key
        return LiteLLMModel(f"openai/{model_name}", base_url, env, "openai")

    raise ValueError(f"unsupported api_type for the LiteLLM mapping: {api_type!r}")


def judge_api_type(base_url: str, api_type: str) -> str:
    """Return the api_type the stdlib judge (``runner.judge``) should use.

    ClawBench's judge speaks only ``openai-completions`` / ``openai-responses`` /
    ``anthropic-messages``. A Gemini model exposed over its OpenAI-compatible
    ``/v1beta/openai`` endpoint must therefore be judged as ``openai-completions``
    (POST ``/chat/completions``); the native ``google-generative-ai`` root is not
    OpenAI-compatible and cannot be a judge. Anthropic/OpenAI types pass through.
    """
    base_url = base_url.rstrip("/")
    if api_type == "google-generative-ai":
        if "/v1beta/openai" in base_url or base_url.endswith("/openai"):
            return "openai-completions"
        raise ValueError(
            "Gemini judge requires an OpenAI-compatible base_url ending in "
            f"'/v1beta/openai'; got {base_url!r}"
        )
    if api_type in ("openai-completions", "openai-responses", "anthropic-messages"):
        return api_type
    raise ValueError(f"unsupported judge api_type: {api_type!r}")
