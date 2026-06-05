"""Tests for clawbench.harbor.model_map (the shared ClawBench↔LiteLLM mapping)."""

from __future__ import annotations

import pytest

from clawbench.harbor import model_map as mm


def test_gemini_native_root_uses_gemini_provider_no_api_base() -> None:
    mapped = mm.build_litellm_model(
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-3.5-flash",
        "google-generative-ai",
        "k",
    )
    assert mapped.model == "gemini/gemini-3.5-flash"
    assert mapped.provider == "gemini"
    # base_url starts with the native Google host -> LiteLLM gemini provider
    # default (no api_base override).
    assert mapped.api_base is None
    assert mapped.env["GEMINI_API_KEY"] == "k"
    assert mapped.env["GOOGLE_API_KEY"] == "k"


def test_anthropic_default_host_has_no_api_base() -> None:
    mapped = mm.build_litellm_model(
        "https://api.anthropic.com",
        "claude-sonnet-4-6",
        "anthropic-messages",
        "k",
    )
    assert mapped.model == "anthropic/claude-sonnet-4-6"
    assert mapped.api_base is None
    assert mapped.env == {"ANTHROPIC_API_KEY": "k"}


def test_anthropic_custom_host_forwards_api_base() -> None:
    mapped = mm.build_litellm_model(
        "https://proxy.example.com",
        "claude-sonnet-4-6",
        "anthropic-messages",
        "k",
    )
    assert mapped.api_base == "https://proxy.example.com"


def test_openai_completions_forwards_base_url_as_api_base() -> None:
    mapped = mm.build_litellm_model(
        "https://api.openai.com/v1/",
        "gpt-5",
        "openai-completions",
        "k",
    )
    assert mapped.model == "openai/gpt-5"
    assert mapped.api_base == "https://api.openai.com/v1"  # trailing slash stripped
    assert mapped.env == {"OPENAI_API_KEY": "k"}
    assert mapped.provider == "openai"


def test_openrouter_sets_env_and_skips_resolution_when_disabled() -> None:
    mapped = mm.build_litellm_model(
        "https://openrouter.ai/api/v1",
        "deepseek/deepseek-v4-flash",
        "openai-completions",
        "k",
        resolve_openrouter=False,
    )
    assert mapped.model == "openrouter/deepseek/deepseek-v4-flash"
    assert mapped.api_base is None
    assert mapped.env["OPENROUTER_API_KEY"] == "k"
    assert mapped.env["OPENROUTER_API_BASE"] == "https://openrouter.ai/api/v1"


def test_unsupported_api_type_raises() -> None:
    with pytest.raises(ValueError):
        mm.build_litellm_model("https://x", "m", "totally-unknown", "k")


def test_pick_api_key_prefers_list_then_single() -> None:
    assert mm.pick_api_key(["a", "b"], "c") == "a"
    assert mm.pick_api_key(None, "c") == "c"
    assert mm.pick_api_key([], "c") == "c"
    with pytest.raises(ValueError):
        mm.pick_api_key(None, None)


def test_pick_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEYS", '["k1", "k2"]')
    monkeypatch.delenv("API_KEY", raising=False)
    assert mm.pick_api_key_from_env() == "k1"
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.setenv("API_KEY", "solo")
    assert mm.pick_api_key_from_env() == "solo"


def test_judge_api_type_gemini_openai_compat() -> None:
    assert (
        mm.judge_api_type(
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "google-generative-ai",
        )
        == "openai-completions"
    )


def test_judge_api_type_gemini_native_root_rejected() -> None:
    with pytest.raises(ValueError):
        mm.judge_api_type(
            "https://generativelanguage.googleapis.com",
            "google-generative-ai",
        )


def test_judge_api_type_passthrough() -> None:
    assert (
        mm.judge_api_type("https://api.openai.com/v1", "openai-completions")
        == "openai-completions"
    )
    assert (
        mm.judge_api_type("https://api.anthropic.com", "anthropic-messages")
        == "anthropic-messages"
    )
    with pytest.raises(ValueError):
        mm.judge_api_type("https://x", "weird-type")
