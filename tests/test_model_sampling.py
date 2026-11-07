"""Regression tests for issue #398: model-dependent Chat Completions fields.

The preflight probe, both LLM judges and the Harbor ``verify.py`` used to
send ``max_tokens`` plus ``temperature: 0`` for every openai-completions
model. OpenAI reasoning models (o-series, GPT-5) reject ``max_tokens``
and an explicit ``temperature``; Kimi K2.x / K3 reject an explicit
``temperature``. These tests pin the fields each call site now sends.
"""

from __future__ import annotations

import json
from typing import Any, Self

import pytest

from clawbench.runner import judge as judge_mod
from clawbench.runner import judge_llm as judge_llm_mod
from clawbench.runner.model_sampling import chat_sampling_fields
from clawbench.runner.run_support.api_preflight import preflight_model_api
from clawbench.runtime.harbor import verify as verify_mod


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-5.4", {"max_completion_tokens": 10}),
        ("gpt-5", {"max_completion_tokens": 10}),
        ("gpt-5.4-mini", {"max_completion_tokens": 10}),
        ("o3-mini", {"max_completion_tokens": 10}),
        ("o4-mini", {"max_completion_tokens": 10}),
        ("openai/gpt-5.2", {"max_completion_tokens": 10}),
        ("kimi-k2.6", {"max_tokens": 10}),
        ("kimi-k3", {"max_tokens": 10}),
        ("moonshot/kimi-k2.5", {"max_tokens": 10}),
        ("gpt-4o", {"max_tokens": 10, "temperature": 0}),
        ("gpt-4.1", {"max_tokens": 10, "temperature": 0}),
        ("deepseek-chat", {"max_tokens": 10, "temperature": 0}),
        ("moonshot-v1-8k", {"max_tokens": 10, "temperature": 0}),
    ],
)
def test_chat_sampling_fields(model: str, expected: dict[str, Any]) -> None:
    assert chat_sampling_fields(model, 10) == expected


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _capture_preflight(monkeypatch: pytest.MonkeyPatch, model: str) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: int) -> _FakeResponse:
        seen.update(json.loads(req.data))
        return _FakeResponse({"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr(
        "clawbench.runner.run_support.api_preflight.urllib.request.urlopen",
        fake_urlopen,
    )
    preflight_model_api(
        {
            "model": model,
            "base_url": "https://api.example.test/v1",
            "api_type": "openai-completions",
            "api_key": "secret-key",
        }
    )
    return seen


def test_preflight_uses_completion_tokens_for_gpt5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _capture_preflight(monkeypatch, "gpt-5.4")
    assert payload["max_completion_tokens"] == 4
    assert "max_tokens" not in payload
    assert "temperature" not in payload


def test_preflight_keeps_legacy_fields_for_gpt4o(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _capture_preflight(monkeypatch, "gpt-4o")
    assert payload["max_tokens"] == 4
    assert payload["temperature"] == 0


def _capture_judge(
    monkeypatch: pytest.MonkeyPatch, module: Any, model: str
) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake_post(url: str, headers: dict, payload: dict, **kw: Any) -> dict:
        seen.update(payload)
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(module, "_post_json", fake_post)
    cfg = {"api_key": "k", "base_url": "https://api.example.test/v1"}
    module._call_openai_chat(cfg, model, "sys", "user")
    return seen


@pytest.mark.parametrize("module", [judge_mod, judge_llm_mod])
def test_judges_omit_temperature_for_kimi(
    monkeypatch: pytest.MonkeyPatch, module: Any
) -> None:
    payload = _capture_judge(monkeypatch, module, "kimi-k2.6")
    assert "temperature" not in payload
    assert "max_tokens" in payload


@pytest.mark.parametrize("module", [judge_mod, judge_llm_mod])
def test_judges_use_completion_tokens_for_reasoning_models(
    monkeypatch: pytest.MonkeyPatch, module: Any
) -> None:
    payload = _capture_judge(monkeypatch, module, "o3-mini")
    assert "max_completion_tokens" in payload
    assert "max_tokens" not in payload
    assert "temperature" not in payload


@pytest.mark.parametrize("module", [judge_mod, judge_llm_mod])
def test_judges_keep_legacy_fields_for_other_models(
    monkeypatch: pytest.MonkeyPatch, module: Any
) -> None:
    payload = _capture_judge(monkeypatch, module, "gpt-4o")
    assert payload["max_tokens"] > 0
    assert payload["temperature"] == 0


def test_harbor_verify_uses_completion_tokens_for_gpt5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_post(url: str, headers: dict, payload: dict, **kw: Any) -> dict:
        seen.update(payload)
        return {"choices": [{"message": {"content": '{"match": true, "reason": "ok"}'}}]}

    monkeypatch.setattr(verify_mod, "post_json", fake_post)
    cfg = {
        "api_type": "openai-completions",
        "model": "gpt-5.4",
        "base_url": "https://api.example.test/v1",
        "api_key": "k",
    }
    verify_mod.call_judge(cfg, "do it", {"url": "https://x", "method": "GET"}, None, "sys", 800)
    assert seen["max_completion_tokens"] == 800
    assert "max_tokens" not in seen
    assert "temperature" not in seen
