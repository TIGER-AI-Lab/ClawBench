"""Tests for the LiteLLM judge api_type (judge.py + judge_llm.py + preflight).

`litellm` is an optional dependency, so we inject a lightweight fake module and
patch its `completion` per test. This lets the suite run without the real
package and lets us assert exactly what gets passed to litellm.completion.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from clawbench.runner import judge, judge_llm
from clawbench.runner.run_support import api_preflight


class _FakeResp(dict):
    """Stand-in for litellm's ModelResponse: supports both ["choices"] and .choices."""

    def __init__(self, content: str):
        super().__init__(choices=[{"message": {"content": content}}])
        self.choices = self["choices"]


def _install_fake_litellm(monkeypatch, content='{"match": true, "reason": "ok"}'):
    calls: list[dict] = []
    fake: Any = types.ModuleType("litellm")

    def completion(**kwargs):
        calls.append(kwargs)
        return _FakeResp(content)

    fake.completion = completion
    monkeypatch.setitem(sys.modules, "litellm", fake)
    return calls


CFG = {
    "base_url": "http://localhost:4000/v1",
    "api_key": "sk-test",
    "api_type": "litellm",
}
INTERCEPT = {"request": {"url": "https://x/api", "method": "POST", "body": {"a": 1}}}


def test_call_litellm_passes_expected_kwargs(monkeypatch) -> None:
    calls = _install_fake_litellm(monkeypatch)
    out = judge._call_litellm(CFG, "gpt-4o-mini", "sys", "user")
    assert out == '{"match": true, "reason": "ok"}'
    kw = calls[0]
    assert kw["model"] == "gpt-4o-mini"
    assert kw["drop_params"] is True
    assert kw["api_base"] == "http://localhost:4000/v1"
    assert kw["api_key"] == "sk-test"
    assert kw["messages"][0]["role"] == "system"
    assert kw["messages"][1]["role"] == "user"


def test_strict_judge_dispatches_litellm(monkeypatch) -> None:
    _install_fake_litellm(monkeypatch, '{"match": false, "reason": "wrong color"}')
    r = judge.judge_request(CFG, "gpt-4o-mini", "buy a red shirt", INTERCEPT)
    assert r["match"] is False
    assert r["judge_model"] == "gpt-4o-mini"


def test_lenient_judge_dispatches_litellm(monkeypatch) -> None:
    _install_fake_litellm(monkeypatch, '{"match": true, "reason": "no contradiction"}')
    r = judge_llm.judge_request(
        CFG, "anthropic/claude-sonnet-4-6", "buy a shirt", INTERCEPT
    )
    assert r["match"] is True
    assert r["rubric"] == "lenient"


def test_preflight_accepts_litellm(monkeypatch) -> None:
    _install_fake_litellm(monkeypatch, "OK")
    # Should not raise.
    api_preflight.preflight_model_api({**CFG, "model": "gpt-4o-mini"})


def test_call_litellm_omits_credentials_when_absent(monkeypatch) -> None:
    calls = _install_fake_litellm(monkeypatch)
    judge._call_litellm({"api_type": "litellm"}, "gpt-4o-mini", "sys", "user")
    kw = calls[0]
    # No base_url/api_key configured -> LiteLLM falls back to provider env vars.
    assert "api_base" not in kw
    assert "api_key" not in kw


def test_call_litellm_raises_without_package(monkeypatch) -> None:
    # Simulate litellm not installed.
    monkeypatch.setitem(sys.modules, "litellm", None)
    with pytest.raises(ImportError, match="litellm"):
        judge._call_litellm(CFG, "gpt-4o-mini", "sys", "user")
