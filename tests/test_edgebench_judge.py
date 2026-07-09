"""Tests for the EdgeBench structured_json judge."""

from __future__ import annotations

import json
from pathlib import Path

from clawbench.eval import edgebench_judge as ej

TASK = {
    "instruction": "Save the recipe",
    "judge_context": {"rubric": "must save"},
    "eval_schema": {"url_pattern": r"target\.example/hit", "method": "GET"},
}
JUDGE_CFG = {
    "base_url": "https://j.example/v1",
    "api_key": "k",
    "api_type": "openai-completions",
}
# a request that actually hits the task target (passes recomputed Stage-1)
GOOD_REQ = {"url": "https://target.example/hit/123", "method": "GET"}
# a request that does NOT match the target (forged / wrong)
BAD_REQ = {"url": "https://other.example/nope", "method": "GET"}


def _evidence(tmp_path: Path, payload) -> Path:
    d = tmp_path / "evidence"
    d.mkdir()
    if payload is not None:
        (d / "interception.json").write_text(json.dumps(payload))
    return d


def _score(tmp_path, payload, **kw):
    return ej.score_evidence(
        TASK, _evidence(tmp_path, payload), judge_cfg=JUDGE_CFG, judge_model="j", **kw
    )


def test_no_evidence_scores_zero(tmp_path: Path) -> None:
    r = _score(tmp_path, None)
    assert r["score"] == 0.0 and r["valid"] is True
    assert r["details"][0] == {"name": "stage1-interception", "status": "FAILED"}


def test_no_request_scores_zero(tmp_path: Path) -> None:
    r = _score(tmp_path, {"intercepted": False})
    assert r["score"] == 0.0 and r["metrics"]["intercepted"] is False


def test_matching_request_passes_stage1_flag_ignored(tmp_path: Path) -> None:
    # "intercepted":"false" is IGNORED — Stage-1 is recomputed from the request,
    # which matches the schema, so it passes.
    r = _score(tmp_path, {"intercepted": "false", "request": GOOD_REQ}, no_judge=True)
    assert r["score"] == 1.0 and r["metrics"]["intercepted"] is True


def test_forged_nonmatching_request_fails(tmp_path: Path) -> None:
    # agent claims intercepted with a request that does NOT hit the target → fail
    r = _score(tmp_path, {"intercepted": True, "request": BAD_REQ})
    assert r["score"] == 0.0
    assert (
        r["details"][0]["status"] == "FAILED" and r["metrics"]["intercepted"] is False
    )


def test_wrong_method_fails(tmp_path: Path) -> None:
    r = _score(
        tmp_path, {"intercepted": True, "request": {**GOOD_REQ, "method": "POST"}}
    )
    assert r["score"] == 0.0


def test_intercepted_no_judge_scores_one(tmp_path: Path) -> None:
    r = _score(tmp_path, {"intercepted": True, "request": GOOD_REQ}, no_judge=True)
    assert r["score"] == 1.0 and r["details"][0]["status"] == "PASSED"


def test_intercepted_judge_match(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ej, "judge_request", lambda *a, **k: {"match": True, "reason": "ok"}
    )
    r = _score(tmp_path, {"intercepted": True, "request": GOOD_REQ})
    assert r["score"] == 1.0 and [d["status"] for d in r["details"]] == [
        "PASSED",
        "PASSED",
    ]


def test_intercepted_judge_mismatch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ej, "judge_request", lambda *a, **k: {"match": False, "reason": "no"}
    )
    r = _score(tmp_path, {"intercepted": True, "request": GOOD_REQ})
    assert r["score"] == 0.0 and r["details"][1]["status"] == "FAILED"


def test_judge_required_but_unconfigured_fails_closed(tmp_path: Path) -> None:
    r = ej.score_evidence(
        TASK,
        _evidence(tmp_path, {"intercepted": True, "request": GOOD_REQ}),
        judge_cfg=None,
        judge_model="j",
    )
    assert r["score"] == 0.0 and r["valid"] is False


def test_missing_eval_schema_fails_closed(tmp_path: Path) -> None:
    r = ej.score_evidence(
        {"instruction": "x"},  # no eval_schema
        _evidence(tmp_path, {"intercepted": True, "request": GOOD_REQ}),
        judge_cfg=JUDGE_CFG,
        judge_model="j",
    )
    assert r["score"] == 0.0 and r["valid"] is False


def test_malformed_evidence_is_invalid(tmp_path: Path) -> None:
    d = tmp_path / "evidence"
    d.mkdir()
    (d / "interception.json").write_text("not json {{{")
    r = ej.score_evidence(TASK, d, judge_cfg=JUDGE_CFG, judge_model="j")
    assert r["score"] == 0.0 and r["valid"] is False


def test_non_object_evidence_is_invalid(tmp_path: Path) -> None:
    r = _score(tmp_path, ["a", "b"])
    assert r["score"] == 0.0 and r["valid"] is False


def test_judge_exception_fails_closed_and_hides_error(
    monkeypatch, tmp_path: Path
) -> None:
    def boom(*a, **k):
        raise RuntimeError("secret-key-abc123 leaked")

    monkeypatch.setattr(ej, "judge_request", boom)
    r = _score(tmp_path, {"intercepted": True, "request": GOOD_REQ})
    assert r["score"] == 0.0 and r["valid"] is False
    assert "secret-key-abc123" not in json.dumps(r)


def test_judge_error_verdict_sanitized(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ej, "judge_request", lambda *a, **k: {"error": "http://p/key=SECRET"}
    )
    r = _score(tmp_path, {"intercepted": True, "request": GOOD_REQ})
    assert r["score"] == 0.0 and "SECRET" not in json.dumps(r)


def test_judge_reason_not_echoed_to_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        ej,
        "judge_request",
        lambda *a, **k: {"match": True, "reason": "body had password=SECRET123"},
    )
    r = _score(tmp_path, {"intercepted": True, "request": GOOD_REQ})
    assert r["score"] == 1.0 and "SECRET123" not in json.dumps(r)


def test_const_fields_match_body() -> None:
    schema = {
        "url_pattern": r"target\.example/hit",
        "method": "POST",
        "body": {"id": 5},
    }
    req_ok = {
        "url": "https://target.example/hit",
        "method": "POST",
        "body": {"id": 5, "x": 1},
    }
    req_bad = {"url": "https://target.example/hit", "method": "POST", "body": {"id": 6}}
    assert ej._stage1_match(req_ok, schema) is True
    assert ej._stage1_match(req_bad, schema) is False


def test_emit_structured_json_round_trips() -> None:
    out = ej.emit_structured_json({"valid": True, "score": 1.0, "metrics": {}})
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
    ev = _evidence(tmp_path, {"intercepted": True, "request": GOOD_REQ})
    rc = ej.main(
        ["--task-json", str(tj), "--evidence-dir", str(ev), "--judge-model", "j"]
    )
    assert rc == 0
    body = (
        capsys.readouterr()
        .out.split(ej.START_MARKER, 1)[1]
        .rsplit(ej.END_MARKER, 1)[0]
        .strip()
    )
    assert json.loads(body)["score"] == 1.0
