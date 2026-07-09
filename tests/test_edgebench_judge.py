"""Tests for the EdgeBench structured_json judge."""

from __future__ import annotations

import json
from pathlib import Path

from clawbench.eval import edgebench_judge as ej

TASK = {"instruction": "Save the recipe", "judge_context": {"rubric": "must save"}}
JUDGE_CFG = {
    "base_url": "https://j.example/v1",
    "api_key": "k",
    "api_type": "openai-completions",
}


def _evidence(tmp_path: Path, payload: dict | None) -> Path:
    d = tmp_path / "evidence"
    d.mkdir()
    if payload is not None:
        (d / "interception.json").write_text(json.dumps(payload))
    return d


def test_no_evidence_scores_zero(tmp_path: Path) -> None:
    r = ej.score_evidence(
        TASK, _evidence(tmp_path, None), judge_cfg=JUDGE_CFG, judge_model="j"
    )
    assert r["score"] == 0.0 and r["valid"] is True
    assert r["details"][0] == {"name": "stage1-interception", "status": "FAILED"}


def test_not_intercepted_scores_zero(tmp_path: Path) -> None:
    r = ej.score_evidence(
        TASK,
        _evidence(tmp_path, {"intercepted": False}),
        judge_cfg=JUDGE_CFG,
        judge_model="j",
    )
    assert r["score"] == 0.0
    assert r["metrics"]["intercepted"] is False


def test_intercepted_no_judge_scores_one(tmp_path: Path) -> None:
    ev = _evidence(tmp_path, {"intercepted": True, "request": {"url": "x"}})
    r = ej.score_evidence(TASK, ev, judge_cfg=JUDGE_CFG, judge_model="j", no_judge=True)
    assert r["score"] == 1.0
    assert r["details"][0]["status"] == "PASSED"


def test_intercepted_judge_match(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ej, "judge_request", lambda *a, **k: {"match": True, "reason": "ok"}
    )
    ev = _evidence(tmp_path, {"intercepted": True, "request": {"url": "x"}})
    r = ej.score_evidence(TASK, ev, judge_cfg=JUDGE_CFG, judge_model="j")
    assert r["score"] == 1.0 and r["valid"] is True
    assert [d["status"] for d in r["details"]] == ["PASSED", "PASSED"]


def test_intercepted_judge_mismatch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ej, "judge_request", lambda *a, **k: {"match": False, "reason": "nope"}
    )
    ev = _evidence(tmp_path, {"intercepted": True, "request": {"url": "x"}})
    r = ej.score_evidence(TASK, ev, judge_cfg=JUDGE_CFG, judge_model="j")
    assert r["score"] == 0.0 and r["details"][1]["status"] == "FAILED"


def test_judge_required_but_unconfigured_fails_closed(tmp_path: Path) -> None:
    ev = _evidence(tmp_path, {"intercepted": True, "request": {"url": "x"}})
    r = ej.score_evidence(TASK, ev, judge_cfg=None, judge_model="j")
    assert r["score"] == 0.0 and r["valid"] is False  # never silently pass


def test_malformed_evidence_is_invalid(tmp_path: Path) -> None:
    d = tmp_path / "evidence"
    d.mkdir()
    (d / "interception.json").write_text("not json {{{")
    r = ej.score_evidence(TASK, d, judge_cfg=JUDGE_CFG, judge_model="j")
    assert r["score"] == 0.0 and r["valid"] is False


def test_non_object_evidence_is_invalid(tmp_path: Path) -> None:
    r = ej.score_evidence(
        TASK, _evidence(tmp_path, ["a", "b"]), judge_cfg=JUDGE_CFG, judge_model="j"
    )
    assert r["score"] == 0.0 and r["valid"] is False


def test_string_false_does_not_pass_stage1(tmp_path: Path) -> None:
    # "intercepted": "false" (truthy string) must NOT count as intercepted
    ev = _evidence(tmp_path, {"intercepted": "false", "request": {"url": "x"}})
    r = ej.score_evidence(TASK, ev, judge_cfg=JUDGE_CFG, judge_model="j", no_judge=True)
    assert r["score"] == 0.0
    assert r["metrics"]["intercepted"] is False


def test_intercepted_without_request_is_invalid(tmp_path: Path) -> None:
    ev = _evidence(tmp_path, {"intercepted": True})
    r = ej.score_evidence(TASK, ev, judge_cfg=JUDGE_CFG, judge_model="j")
    assert r["score"] == 0.0 and r["valid"] is False


def test_judge_exception_fails_closed_and_hides_error(
    monkeypatch, tmp_path: Path
) -> None:
    def boom(*a, **k):
        raise RuntimeError("secret-key-abc123 leaked in exception")

    monkeypatch.setattr(ej, "judge_request", boom)
    ev = _evidence(tmp_path, {"intercepted": True, "request": {"url": "x"}})
    r = ej.score_evidence(TASK, ev, judge_cfg=JUDGE_CFG, judge_model="j")
    assert r["score"] == 0.0 and r["valid"] is False
    assert "secret-key-abc123" not in json.dumps(r)  # raw error not echoed


def test_judge_error_verdict_sanitized(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ej, "judge_request", lambda *a, **k: {"error": "http://provider/key=SECRET"}
    )
    ev = _evidence(tmp_path, {"intercepted": True, "request": {"url": "x"}})
    r = ej.score_evidence(TASK, ev, judge_cfg=JUDGE_CFG, judge_model="j")
    assert r["score"] == 0.0 and "SECRET" not in json.dumps(r)


def test_judge_reason_not_echoed_to_output(monkeypatch, tmp_path: Path) -> None:
    # the judge reason quotes the request body (may hold creds/PII) — must not leak
    monkeypatch.setattr(
        ej,
        "judge_request",
        lambda *a, **k: {"match": True, "reason": "body had password=SECRET123"},
    )
    ev = _evidence(tmp_path, {"intercepted": True, "request": {"url": "x"}})
    r = ej.score_evidence(TASK, ev, judge_cfg=JUDGE_CFG, judge_model="j")
    assert r["score"] == 1.0 and "SECRET123" not in json.dumps(r)


def test_emit_structured_json_round_trips() -> None:
    r = {"valid": True, "score": 1.0, "summary": "s", "details": [], "metrics": {}}
    out = ej.emit_structured_json(r)
    assert out.startswith(ej.START_MARKER) and out.rstrip().endswith(ej.END_MARKER)
    body = out.split(ej.START_MARKER, 1)[1].rsplit(ej.END_MARKER, 1)[0].strip()
    assert json.loads(body)["score"] == 1.0


def test_cli_main_prints_structured_block(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        ej, "judge_request", lambda *a, **k: {"match": True, "reason": "ok"}
    )
    monkeypatch.setenv("CLAWBENCH_JUDGE_BASE_URL", "https://j.example/v1")
    monkeypatch.setenv("CLAWBENCH_JUDGE_API_KEY", "k")
    tj = tmp_path / "task.json"
    tj.write_text(json.dumps(TASK))
    ev = _evidence(tmp_path, {"intercepted": True, "request": {"url": "x"}})
    rc = ej.main(
        ["--task-json", str(tj), "--evidence-dir", str(ev), "--judge-model", "j"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert ej.START_MARKER in out
    body = out.split(ej.START_MARKER, 1)[1].rsplit(ej.END_MARKER, 1)[0].strip()
    assert json.loads(body)["score"] == 1.0
