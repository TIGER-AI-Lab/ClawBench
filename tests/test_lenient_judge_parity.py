"""The lenient rubric must reach the judge transport identically to the strict one.

judge_llm.py used to re-implement _post_json / _build_user_msg / the api_type
dispatch. That copy drifted: no judge_context, openai-responses routed at
/chat/completions, google-generative-ai unsupported, and max_tokens capped at
800 (a reasoning judge truncates and lands on the inconclusive path). These
tests pin the collapsed behaviour so the two rubrics cannot diverge again.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from clawbench.runner import judge, judge_llm


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record every HTTP payload the judge would send, without a network."""
    calls: list[dict[str, Any]] = []

    def fake_post(
        url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int = 60
    ) -> dict[str, Any]:
        calls.append({"url": url, "headers": headers, "payload": payload})
        return {
            "choices": [{"message": {"content": '{"match": true, "reason": "ok"}'}}],
            "output_text": '{"match": true, "reason": "ok"}',
            "content": [{"type": "text", "text": '{"match": true, "reason": "ok"}'}],
        }

    monkeypatch.setattr(judge, "_post_json", fake_post)
    return calls


INTERCEPT = {"request": {"url": "https://shop.test/cart", "method": "POST", "body": {}}}


def _cfg(api_type: str, base_url: str = "https://api.test/v1") -> dict[str, Any]:
    return {"api_type": api_type, "base_url": base_url, "api_key": "k"}


# --- the four documented divergences ----------------------------------------


def test_lenient_judge_accepts_judge_context(captured: list[dict[str, Any]]) -> None:
    """run.py passes judge_context to the strict judge; the lenient signature
    used to reject it outright with a TypeError."""
    judge_llm.judge_request(
        _cfg("openai-completions"),
        "judge-model",
        "buy a red shirt",
        INTERCEPT,
        judge_context={"rubric": "must be red"},
    )

    user_msg = captured[0]["payload"]["messages"][1]["content"]
    assert "HIDDEN JUDGE CONTEXT" in user_msg
    assert "must be red" in user_msg


def test_lenient_judge_routes_openai_responses_to_the_responses_endpoint(
    captured: list[dict[str, Any]],
) -> None:
    judge_llm.judge_request(_cfg("openai-responses"), "m", "do a thing", INTERCEPT)

    assert captured[0]["url"].endswith("/responses")


def test_lenient_judge_supports_gemini(captured: list[dict[str, Any]]) -> None:
    """google-generative-ai used to raise NotImplementedError on this path."""
    verdict = judge_llm.judge_request(
        _cfg("google-generative-ai", "https://generativelanguage.googleapis.com"),
        "gemini-3-pro",
        "do a thing",
        INTERCEPT,
    )

    assert verdict["match"] is True
    assert "/v1beta/openai/chat/completions" in captured[0]["url"]


@pytest.mark.parametrize(
    "api_type", ["openai-completions", "openai-responses", "anthropic-messages"]
)
def test_lenient_judge_gives_a_reasoning_judge_room_to_answer(
    api_type: str, captured: list[dict[str, Any]]
) -> None:
    """The default judge is a reasoning model that burns hidden tokens before
    emitting its JSON line; 800 truncated it into the inconclusive path."""
    judge_llm.judge_request(_cfg(api_type), "m", "do a thing", INTERCEPT)

    payload = captured[0]["payload"]
    budget = payload.get("max_tokens") or payload.get("max_output_tokens")
    assert budget == 4096


# --- the rubrics stay distinct in the one way they should --------------------


def test_the_two_rubrics_differ_only_in_the_system_prompt(
    captured: list[dict[str, Any]],
) -> None:
    args = (_cfg("openai-completions"), "m", "buy a red shirt", INTERCEPT)

    judge.judge_request(*args)
    judge_llm.judge_request(*args)

    strict, lenient = captured
    assert strict["payload"]["messages"][0]["content"] == judge.JUDGE_SYSTEM
    assert lenient["payload"]["messages"][0]["content"] == judge_llm.JUDGE_SYSTEM
    assert "strict evaluator" in judge.JUDGE_SYSTEM
    assert "lenient evaluator" in judge_llm.JUDGE_SYSTEM

    # everything else on the wire is identical
    assert strict["url"] == lenient["url"]
    assert strict["headers"] == lenient["headers"]
    assert strict["payload"]["messages"][1] == lenient["payload"]["messages"][1]
    assert strict["payload"]["max_tokens"] == lenient["payload"]["max_tokens"]


def test_lenient_verdict_is_tagged_with_its_rubric(
    captured: list[dict[str, Any]],
) -> None:
    verdict = judge_llm.judge_request(_cfg("openai-completions"), "m", "x", INTERCEPT)

    assert verdict["rubric"] == "lenient"
    assert set(
        judge.judge_request(_cfg("openai-completions"), "m", "x", INTERCEPT)
    ) <= set(verdict)


def test_lenient_signature_matches_the_strict_one() -> None:
    """rescore.py calls both through one dict of judge functions."""
    strict = inspect.signature(judge.judge_request)
    lenient = inspect.signature(judge_llm.judge_request)

    assert list(strict.parameters) == list(lenient.parameters)
    for name, param in strict.parameters.items():
        assert lenient.parameters[name].kind == param.kind
        assert lenient.parameters[name].default == param.default


def test_lenient_module_no_longer_reimplements_the_transport() -> None:
    """Regression guard for the duplication itself: the ~100 copied lines of
    _post_json / _call_* are what drifted in the first place."""
    src = inspect.getsource(judge_llm)

    for copied in ("def _post_json", "def _call_openai_chat", "def _build_user_msg"):
        assert copied not in src
