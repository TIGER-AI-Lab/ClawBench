"""Tests for the answer/rubric judge (judge_answer) + the shared dispatch refactor."""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from clawbench.runner import judge
from clawbench.utils.paths import asset_path

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


def _judge_context_schema() -> dict:
    path = asset_path("test-cases", "task.schema.json")
    if not path.is_file():
        pytest.skip("bundled task.schema.json not available")
    schema = json.loads(path.read_text(encoding="utf-8"))
    return schema["properties"]["judge_context"]


def test_schema_declares_every_key_the_answer_judge_reads() -> None:
    """A key the judge reads but the schema omits is unreachable.

    judge_context sets additionalProperties: false, so a task carrying an
    undeclared key fails both validate-task in CI and any local validation.
    gold_answer was in exactly that state: read here, documented in
    docs/answer-mode-tasks.md, rejected by the schema.
    """
    declared = set(_judge_context_schema()["properties"])
    missing = set(judge.ANSWER_CONTEXT_KEYS) - declared
    assert missing == set(), (
        f"judge_context keys read by the answer judge but not declared in "
        f"task.schema.json: {sorted(missing)}"
    )


def test_schema_declares_no_judge_context_key_no_judge_reads() -> None:
    """The reverse drift: a schema field nothing consumes is a promise we break."""
    declared = set(_judge_context_schema()["properties"])
    request_keys = {"rubric", "reference_solution", "source_task_yaml"}
    consumed = set(judge.ANSWER_CONTEXT_KEYS) | request_keys
    assert declared - consumed == set()
    # The request judge's keys are a literal list in _context_text; if that
    # changes, this constant has to change with it.
    for key in request_keys:
        assert key in judge._context_text.__code__.co_consts


def test_a_task_carrying_a_gold_answer_validates() -> None:
    validator = Draft202012Validator(
        json.loads(
            asset_path("test-cases", "task.schema.json").read_text(encoding="utf-8")
        )
    )
    task = {
        "instruction": "What is the capital of France?",
        "eval_schema": {"url_pattern": "/api/task-submit", "method": "POST"},
        "time_limit": 10,
        "judge_context": {"gold_answer": "Paris", "rubric": "exact city name"},
    }
    assert list(validator.iter_errors(task)) == []


def test_gold_answer_reaches_the_judge_labelled_by_its_key() -> None:
    """The judge sees the key name, so gold_answer and reference_solution differ."""
    msg = judge._build_answer_msg("q", "Lyon", {"gold_answer": "Paris"})
    assert "gold_answer:\nParis" in msg
