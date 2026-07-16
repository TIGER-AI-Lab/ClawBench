"""Tests for the answer/rubric judge (judge_answer) + the shared dispatch refactor."""

from __future__ import annotations

from clawbench.runner import judge

CFG = {
    "base_url": "https://j.example/v1",
    "api_key": "k",
    "api_type": "openai-completions",
}


def _mock_post(monkeypatch, content: str):
    def fake_post(url, headers, payload):
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(judge, "_post_json", fake_post)


def test_judge_answer_match(monkeypatch) -> None:
    _mock_post(monkeypatch, '{"match": true, "reason": "answer is correct"}')
    r = judge.judge_answer(
        CFG, "m", "What is 2+2?", "4", judge_context={"rubric": "must be 4"}
    )
    assert r["match"] is True and r["error"] is None


def test_judge_answer_mismatch(monkeypatch) -> None:
    _mock_post(monkeypatch, '{"match": false, "reason": "wrong"}')
    r = judge.judge_answer(CFG, "m", "What is 2+2?", "5")
    assert r["match"] is False


def test_build_answer_msg_includes_answer_and_rubric() -> None:
    msg = judge._build_answer_msg(
        "do the thing",
        "my final answer",
        {"rubric": "must include X", "gold_answer": "X"},
    )
    assert "do the thing" in msg
    assert "my final answer" in msg
    assert "RUBRIC" in msg and "must include X" in msg and "X" in msg


def test_build_answer_msg_handles_empty_answer() -> None:
    msg = judge._build_answer_msg("inst", "", None)
    assert "no answer" in msg.lower()


def test_answer_judge_unsupported_api_type() -> None:
    r = judge.judge_answer(
        {"base_url": "http://x", "api_key": "k", "api_type": "bogus"}, "m", "i", "a"
    )
    assert r["match"] is None and r["error"] == "unsupported_api_type"


def test_judge_request_still_works_after_refactor(monkeypatch) -> None:
    # the refactor to _run_judge must not change judge_request behaviour
    _mock_post(monkeypatch, '{"match": true, "reason": "ok"}')
    r = judge.judge_request(
        CFG, "m", "book it", {"request": {"url": "x", "method": "POST"}}
    )
    assert r["match"] is True and r["judge_model"] == "m"


def test_run_judge_is_shared() -> None:
    assert callable(judge._run_judge)
    # both judges route through it
    assert "_run_judge" in judge.judge_request.__code__.co_names
    assert "_run_judge" in judge.judge_answer.__code__.co_names
