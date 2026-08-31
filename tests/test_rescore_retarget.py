"""Regression test for issue #299, ask 3: clawbench-rescore must retarget a
run whose cached judge verdict is `match: null` (the judge never rendered a
verdict last time) even without --force, since that cached file is not a
scored result: it is the same outage this issue is about, just replayed
from disk instead of from a live judge call.
"""

from __future__ import annotations

import json
from pathlib import Path

from clawbench.eval.rescore import rescore_one


def _make_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "model-a" / "run-1"
    (run_dir / "data").mkdir(parents=True)
    (run_dir / "run-meta.json").write_text(
        json.dumps({"intercepted": True, "instruction": "do the task"})
    )
    (run_dir / "data" / "interception.json").write_text(
        json.dumps({"request": {"url": "https://example.test"}})
    )
    return run_dir


def test_cached_inconclusive_verdict_is_retried_without_force(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    (run_dir / "judge.json").write_text(
        json.dumps({"match": None, "reason": "judge_call_failed: timeout"})
    )

    calls = []

    def fake_judge(model_cfg, judge_model, instruction, intercept):
        calls.append(1)
        return {"match": True, "reason": "fulfills it"}

    out = rescore_one(
        model_cfg={},
        judge_model="judge-a",
        run_dir=run_dir,
        force=False,
        rubrics=["strict"],
        judge_funcs={"strict": fake_judge},
    )

    assert len(calls) == 1  # retried despite force=False
    assert out["strict"]["match"] is True


def test_cached_scored_verdict_is_not_retried_without_force(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    (run_dir / "judge.json").write_text(
        json.dumps({"match": False, "reason": "did not fulfill it"})
    )

    calls = []

    def fake_judge(model_cfg, judge_model, instruction, intercept):
        calls.append(1)
        return {"match": True, "reason": "should not be reached"}

    out = rescore_one(
        model_cfg={},
        judge_model="judge-a",
        run_dir=run_dir,
        force=False,
        rubrics=["strict"],
        judge_funcs={"strict": fake_judge},
    )

    assert calls == []  # cached scored verdict wins, no retry
    assert out["strict"]["match"] is False
