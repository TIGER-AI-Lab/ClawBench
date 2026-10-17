"""A corrupt judge cache must not prevent CLI rescoring (issue #364)."""

import json
import sys
from pathlib import Path

import pytest

from clawbench.eval import rescore
from clawbench.runner import judge, judge_llm


def _run(tmp_path: Path) -> Path:
    run = tmp_path / "batch-test" / "run-1"
    (run / "data").mkdir(parents=True)
    (run / "run-meta.json").write_text(
        json.dumps({"intercepted": True, "instruction": "do it", "task_id": "task-1"})
    )
    (run / "data" / "interception.json").write_text(json.dumps({"request": {}}))
    return run


def _main(tmp_path: Path, monkeypatch, rubric: str) -> int:
    models = tmp_path / "models.yaml"
    models.write_text("test-judge:\n  api_key: dummy\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clawbench-rescore",
            "--only-batch",
            str(tmp_path / "batch-test"),
            "--models-yaml",
            str(models),
            "--judge-model",
            "test-judge",
            "--rubric",
            rubric,
            "--workers",
            "1",
            "--no-eval-results",
        ],
    )
    return rescore.main()


@pytest.mark.parametrize(
    "bad_cache", ['{"match":', "[]", '{"match": "true"}', '{"match": null}']
)
def test_cli_retries_unusable_strict_cache(tmp_path, monkeypatch, capsys, bad_cache):
    run = _run(tmp_path)
    (run / "judge.json").write_text(bad_cache)
    calls = []

    def fake_judge(*args):
        calls.append(1)
        return {"match": True, "reason": "fresh"}

    monkeypatch.setattr(judge, "judge_request", fake_judge)
    assert _main(tmp_path, monkeypatch, "strict") == 0
    assert calls == [1]
    assert json.loads((run / "judge.json").read_text())["reason"] == "fresh"
    assert "retrying" in capsys.readouterr().err


def test_both_rubrics_only_retries_corrupt_one(tmp_path, monkeypatch):
    run = _run(tmp_path)
    (run / "judge_llm.json").write_text('{"match": false, "reason": "keep"}')
    (run / "judge.json").write_text('{"match":')
    calls = []

    def fake_strict(*args):
        calls.append("strict")
        return {"match": True, "reason": "fresh"}

    monkeypatch.setattr(judge, "judge_request", fake_strict)
    monkeypatch.setattr(
        judge_llm, "judge_request", lambda *args: calls.append("lenient")
    )
    assert _main(tmp_path, monkeypatch, "both") == 0
    assert calls == ["strict"]
    assert json.loads((run / "judge_llm.json").read_text())["reason"] == "keep"
    summary = json.loads((tmp_path / "batch-test" / "rescore-summary.json").read_text())
    assert summary["n_match_strict"] == 1
    assert summary["n_mismatch_lenient"] == 1


def test_atomic_write_keeps_previous_cache_on_replace_failure(tmp_path, monkeypatch):
    cache = tmp_path / "judge.json"
    cache.write_text('{"match": true, "reason": "old"}')

    def fail_replace(*args):
        raise OSError("replace failed")

    monkeypatch.setattr(rescore.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        rescore._write_verdict(cache, {"match": False, "reason": "new"})
    assert json.loads(cache.read_text())["reason"] == "old"
    assert list(tmp_path.glob("*.tmp")) == []


def test_cli_reports_incomplete_rescore(tmp_path, monkeypatch, capsys):
    run = _run(tmp_path)
    (run / "judge.json").write_text('{"match":')

    def fail_judge(*args):
        raise RuntimeError("judge unavailable")

    monkeypatch.setattr(judge, "judge_request", fail_judge)
    assert _main(tmp_path, monkeypatch, "strict") == 1
    err = capsys.readouterr().err
    assert "judge unavailable" in err
    assert "rescore incomplete" in err
