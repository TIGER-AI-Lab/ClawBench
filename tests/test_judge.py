"""Tests for the LLM judge, incl. Gemini (google-generative-ai) routing (#247)."""

from __future__ import annotations

import pytest

from clawbench.runner import judge, judge_llm
from clawbench.runtime.harbor.body import render_body


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


# --- verdict parsing (see #295) -------------------------------------------
#
# The `match` field decides whether a run counts as a pass, so it has to be
# read exactly. Models answer with real booleans, with the *strings* "true"
# and "false", and sometimes with no verdict at all — `bool("false")` is True,
# so a stringly-typed mismatch used to be scored as a pass.


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # real booleans
        ('{"match": true, "reason": "ok"}', True),
        ('{"match": false, "reason": "wrong item"}', False),
        # stringly-typed verdicts — the regression this pins
        ('{"match": "false", "reason": "wrong item"}', False),
        ('{"match": "true"}', True),
        ('{"match": "FALSE"}', False),
        ('{"match": "False"}', False),
        # no usable verdict → inconclusive, never an implicit pass/fail
        ('{"reason": "forgot the verdict"}', None),
        ('{"match": null}', None),
        ('{"match": "maybe"}', None),
        # fenced JSON still parses
        ('```json\n{"match": false, "reason": "r"}\n```', False),
    ],
)
def test_parse_verdict_is_tri_state(raw: str, expected: bool | None) -> None:
    assert judge._parse_verdict(raw)[0] is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"match": "false", "reason": "wrong item"}', False),
        ('{"match": false}', False),
        ('{"match": true}', True),
        # a reply with no verdict key must not default to a pass: this module
        # produces the published Reward-lenient column
        ('{"reason": "forgot the verdict"}', None),
        ("not json at all", None),
    ],
)
def test_lenient_judge_parse_verdict_is_tri_state(
    raw: str, expected: bool | None
) -> None:
    assert judge_llm._parse_verdict(raw)[0] is expected


def test_coerce_match_rejects_non_verdict_types() -> None:
    for value in (1, 0, [], {}, None, "  "):
        assert judge._coerce_match(value) is None


def test_shared_body_renderer_reports_truncation() -> None:
    assert render_body(None).prompt_text() == "(empty)"
    assert render_body("").prompt_text() == ""

    complete = render_body("x" * 6000)
    assert complete.truncated is False
    assert complete.original_length == 6000
    assert complete.prompt_text() == "x" * 6000

    rendered = render_body("x" * 6000 + "tail")

    assert rendered.text == "x" * 6000
    assert rendered.original_length == 6004
    assert rendered.omitted_length == 4
    assert rendered.truncated is True
    prompt = rendered.prompt_text().lower()
    assert "body was truncated" in prompt
    assert "original body length was 6004" in prompt
    assert "4 characters were omitted" in prompt
    assert "insufficient evidence for a positive lenient match" in prompt


def test_lenient_judge_rejects_positive_match_for_truncated_body(monkeypatch) -> None:
    body = "x" * 6000 + '{"color":"blue"}'
    seen = {}

    def fake_call(model_cfg, model_name, system, user):
        seen["user"] = user
        return '{"match": true, "reason": "no contradiction visible"}'

    monkeypatch.setattr(judge_llm, "_call_openai_chat", fake_call)
    verdict = judge_llm.judge_request(
        {"base_url": "https://judge.example/v1", "api_key": "key"},
        "judge",
        "Choose a red shirt",
        {
            "request": {
                "url": "https://example.test/submit",
                "method": "POST",
                "body": body,
            }
        },
    )

    assert verdict["match"] is False
    assert verdict["body_truncated"] is True
    assert verdict["body_length"] == len(body)
    prompt = seen["user"].lower()
    assert "body was truncated" in prompt
    assert "insufficient evidence for a positive lenient match" in prompt


def test_strict_judge_records_body_metadata_and_notice(monkeypatch) -> None:
    body = "x" * 6000 + "tail"
    seen = {}

    def fake_call(model_cfg, model_name, system, user):
        seen["user"] = user
        return '{"match": false, "reason": "incomplete evidence"}'

    monkeypatch.setattr(judge, "_call_openai_chat", fake_call)
    verdict = judge.judge_request(
        {"base_url": "https://judge.example/v1", "api_key": "key"},
        "judge",
        "Do the task",
        {"request": {"body": body}},
    )

    assert verdict["match"] is False
    assert verdict["body_truncated"] is True
    assert verdict["body_length"] == len(body)
    assert "body was truncated" in seen["user"].lower()
