"""Tests for the LLM judge, incl. Gemini (google-generative-ai) routing (#247)."""

from __future__ import annotations

from clawbench.runner import judge


def test_gemini_openai_cfg_normalizes_native_root() -> None:
    # native Google root → OpenAI-compat path appended
    cfg = judge._gemini_openai_cfg(
        {"base_url": "https://generativelanguage.googleapis.com/", "api_key": "k"}
    )
    assert cfg["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai"
    # already an /openai path → left as-is
    cfg2 = judge._gemini_openai_cfg(
        {
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "api_key": "k",
        }
    )
    assert cfg2["base_url"].endswith("/v1beta/openai")


def test_gemini_judge_routes_through_openai_compat(monkeypatch) -> None:
    seen = {}

    def fake_post(url, headers, payload):
        seen["url"] = url
        return {
            "choices": [{"message": {"content": '{"match": true, "reason": "ok"}'}}]
        }

    monkeypatch.setattr(judge, "_post_json", fake_post)
    cfg = {
        "base_url": "https://generativelanguage.googleapis.com",  # native root
        "api_key": "k",
        "api_type": "google-generative-ai",
    }
    r = judge.judge_request(cfg, "gemini-3.5-flash", "do it", {"request": {"url": "x"}})
    assert r["match"] is True
    # hit the OpenAI-compat chat endpoint, not the native root
    assert seen["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )


def test_unsupported_api_type_reports_error(monkeypatch) -> None:
    r = judge.judge_request(
        {"base_url": "http://x", "api_key": "k", "api_type": "bogus-type"},
        "m",
        "do it",
        {"request": {"url": "x"}},
    )
    assert r["match"] is None and r["error"] == "unsupported_api_type"
