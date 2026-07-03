"""Lightweight host-side model API preflight checks."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class ModelApiPreflightError(RuntimeError):
    """Raised when a configured model API cannot satisfy a tiny test call."""


def _api_key(model_cfg: dict[str, Any]) -> str:
    keys = model_cfg.get("api_keys")
    if isinstance(keys, list) and keys:
        return str(keys[0])
    key = model_cfg.get("api_key")
    if key:
        return str(key)
    raise ModelApiPreflightError("missing API key")


def _redact(text: str, secrets: list[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret and len(secret) >= 4:
            variants = {
                secret,
                urllib.parse.quote(secret, safe=""),
                urllib.parse.quote_plus(secret, safe=""),
            }
            for variant in variants:
                redacted = redacted.replace(variant, "[REDACTED]")
    return redacted


def _error_message(prefix: str, exc: Exception, secrets: list[str]) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        detail = f"HTTP {exc.code} {exc.reason}"
    elif isinstance(exc, urllib.error.URLError):
        detail = str(exc.reason)
    else:
        detail = str(exc)
    detail = _redact(detail, secrets).strip()
    return f"{prefix}: {detail or type(exc).__name__}"


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    *,
    timeout: int,
    secrets: list[str],
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            **headers,
            "Content-Type": "application/json",
            "User-Agent": "clawbench/preflight",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except Exception as exc:
        raise ModelApiPreflightError(
            _error_message("model API request failed", exc, secrets)
        ) from None
    try:
        loaded = json.loads(body)
    except json.JSONDecodeError:
        raise ModelApiPreflightError("model API returned invalid JSON") from None
    if not isinstance(loaded, dict):
        raise ModelApiPreflightError("model API returned non-object JSON")
    return loaded


def _expect_field(condition: bool, message: str) -> None:
    if not condition:
        raise ModelApiPreflightError(message)


def _gemini_url(base_url: str, model: str, api_key: str) -> str:
    base = base_url.rstrip("/")
    parsed = urllib.parse.urlsplit(base)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1") or path.endswith("/v1beta"):
        api_base = base
    else:
        api_base = f"{base}/v1beta"
    quoted_model = urllib.parse.quote(model, safe="/-_.:")
    query = urllib.parse.urlencode({"key": api_key})
    return f"{api_base}/models/{quoted_model}:generateContent?{query}"


def preflight_model_api(model_cfg: dict[str, Any], timeout: int = 20) -> None:
    """Make one tiny API call to catch invalid model config before containers run."""

    model = str(model_cfg.get("model") or "").strip()
    base_url = str(model_cfg.get("base_url") or "").rstrip("/")
    api_type = str(model_cfg.get("api_type") or "").strip()
    key = _api_key(model_cfg)
    secrets = [key]
    test_content = "Reply with OK."
    if not model:
        raise ModelApiPreflightError("missing model name")
    if not base_url:
        raise ModelApiPreflightError("missing base_url")
    if not api_type:
        raise ModelApiPreflightError("missing api_type")

    if api_type == "openai-completions":
        resp = _post_json(
            f"{base_url}/chat/completions",
            {"Authorization": f"Bearer {key}"},
            {
                "model": model,
                "messages": [{"role": "user", "content": test_content}],
                "max_tokens": 4,
                "temperature": 0,
            },
            timeout=timeout,
            secrets=secrets,
        )
        _expect_field(
            isinstance(resp.get("choices"), list) and bool(resp["choices"]),
            "model API returned no chat choices",
        )
    elif api_type == "openai-responses":
        resp = _post_json(
            f"{base_url}/responses",
            {"Authorization": f"Bearer {key}"},
            {
                "model": model,
                "input": test_content,
                "max_output_tokens": 4,
            },
            timeout=timeout,
            secrets=secrets,
        )
        _expect_field(
            bool(resp.get("output") or resp.get("output_text")),
            "model API returned no response output",
        )
    elif api_type == "anthropic-messages":
        resp = _post_json(
            f"{base_url}/v1/messages",
            {
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            {
                "model": model,
                "max_tokens": 4,
                "messages": [{"role": "user", "content": test_content}],
            },
            timeout=timeout,
            secrets=secrets,
        )
        _expect_field(
            isinstance(resp.get("content"), list) and bool(resp["content"]),
            "model API returned no message content",
        )
    elif api_type == "google-generative-ai":
        resp = _post_json(
            _gemini_url(base_url, model, key),
            {},
            {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": test_content}],
                    }
                ],
                "generationConfig": {
                    "maxOutputTokens": 4,
                    "temperature": 0,
                },
            },
            timeout=timeout,
            secrets=secrets,
        )
        _expect_field(
            isinstance(resp.get("candidates"), list) and bool(resp["candidates"]),
            "model API returned no Gemini candidates",
        )
    else:
        raise ModelApiPreflightError(f"unsupported api_type {api_type!r}")
