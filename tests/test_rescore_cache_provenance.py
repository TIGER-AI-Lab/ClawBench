"""Regression test for issue #363: a cached judge verdict must only be reused
when it was produced under the same judge (model + non-secret config), rubric,
instruction and intercepted evidence as the current request. Before this fix,
`rescore_one`'s cache-hit check only looked at `match is not None`, so a run
judged once by an old judge kept reporting that old verdict, mislabeled as the
newly requested judge, with zero live judge calls made.
"""

from __future__ import annotations

import json
from pathlib import Path

from clawbench.eval.rescore import (
    _cache_fingerprint,
    _cache_is_stale,
    aggregate_batch,
    rescore_one,
)


def test_cache_is_stale_on_missing_match_or_fingerprint_mismatch() -> None:
    fingerprint = _cache_fingerprint("judge-a", {}, "strict", "do it", {"a": 1})
    other_fingerprint = _cache_fingerprint("judge-b", {}, "strict", "do it", {"a": 1})

    assert _cache_is_stale(
        {"match": None, "cache_fingerprint": fingerprint}, fingerprint
    )
    assert _cache_is_stale(
        {"match": True}, fingerprint
    )  # no fingerprint recorded (legacy)
    assert _cache_is_stale(
        {"match": True, "cache_fingerprint": other_fingerprint}, fingerprint
    )
    assert not _cache_is_stale(
        {"match": True, "cache_fingerprint": fingerprint}, fingerprint
    )


def _make_run_dir(tmp_path: Path, name: str = "run-1") -> Path:
    run_dir = tmp_path / "model-a" / name
    (run_dir / "data").mkdir(parents=True)
    (run_dir / "run-meta.json").write_text(
        json.dumps({"intercepted": True, "instruction": "do the task", "task_id": name})
    )
    (run_dir / "data" / "interception.json").write_text(
        json.dumps({"request": {"url": "https://example.test"}})
    )
    return run_dir


def test_cache_from_a_different_judge_model_is_not_reused(tmp_path: Path) -> None:
    """Issue #363's own verified reproduction: an old-judge cache must not be
    silently attributed to a newly requested judge."""
    run_dir = _make_run_dir(tmp_path)
    (run_dir / "judge.json").write_text(
        json.dumps({"match": True, "reason": "old verdict", "judge_model": "old-judge"})
    )

    calls = []

    def fake_judge(model_cfg, judge_model, instruction, intercept):
        calls.append(judge_model)
        return {"match": True, "reason": "fresh verdict", "judge_model": judge_model}

    out = rescore_one(
        model_cfg={},
        judge_model="new-judge",
        run_dir=run_dir,
        force=False,
        rubrics=["strict"],
        judge_funcs={"strict": fake_judge},
    )

    assert calls == ["new-judge"]  # recomputed, not silently reused
    assert out["strict"]["judge_model"] == "new-judge"


def test_legacy_cache_with_no_fingerprint_is_not_reused(tmp_path: Path) -> None:
    """A cache written before this fix (or by the initial run, which never set
    `cache_fingerprint`) has unknown provenance and must be recomputed, not
    trusted just because `match` is set."""
    run_dir = _make_run_dir(tmp_path)
    (run_dir / "judge.json").write_text(
        json.dumps({"match": True, "reason": "legacy verdict"})
    )

    calls = []

    def fake_judge(model_cfg, judge_model, instruction, intercept):
        calls.append(1)
        return {"match": True, "reason": "fresh verdict", "judge_model": judge_model}

    out = rescore_one(
        model_cfg={},
        judge_model="judge-a",
        run_dir=run_dir,
        force=False,
        rubrics=["strict"],
        judge_funcs={"strict": fake_judge},
    )

    assert len(calls) == 1
    assert out["strict"]["reason"] == "fresh verdict"


def test_cache_with_a_different_instruction_is_not_reused(tmp_path: Path) -> None:
    """Same judge, same rubric, but the task's instruction changed since the
    cache was written (e.g. a corrected task.json), so the cache no longer
    describes this evaluation."""
    run_dir = tmp_path / "model-a" / "run-1"
    (run_dir / "data").mkdir(parents=True)
    (run_dir / "run-meta.json").write_text(
        json.dumps({"intercepted": True, "instruction": "do the NEW task"})
    )
    (run_dir / "data" / "interception.json").write_text(
        json.dumps({"request": {"url": "https://example.test"}})
    )
    stale_fingerprint = _cache_fingerprint(
        "judge-a",
        {},
        "strict",
        "do the OLD task",
        {"request": {"url": "https://example.test"}},
    )
    (run_dir / "judge.json").write_text(
        json.dumps(
            {
                "match": True,
                "reason": "matched the old instruction",
                "cache_fingerprint": stale_fingerprint,
            }
        )
    )

    calls = []

    def fake_judge(model_cfg, judge_model, instruction, intercept):
        calls.append(instruction)
        return {"match": False, "reason": "does not match new instruction"}

    out = rescore_one(
        model_cfg={},
        judge_model="judge-a",
        run_dir=run_dir,
        force=False,
        rubrics=["strict"],
        judge_funcs={"strict": fake_judge},
    )

    assert calls == ["do the NEW task"]
    assert out["strict"]["match"] is False


def test_cache_from_a_different_judge_config_is_not_reused(tmp_path: Path) -> None:
    """Same judge model key, but its resolved config changed (e.g. `base_url`
    repointed to a different provider, or `thinking_level` changed), so the
    verdict is no longer known to come from the same judge behavior."""
    run_dir = _make_run_dir(tmp_path)
    old_cfg = {"base_url": "https://old.example", "api_type": "openai-completions"}
    new_cfg = {"base_url": "https://new.example", "api_type": "openai-completions"}
    old_fingerprint = _cache_fingerprint(
        "judge-a",
        old_cfg,
        "strict",
        "do the task",
        {"request": {"url": "https://example.test"}},
    )
    (run_dir / "judge.json").write_text(
        json.dumps(
            {
                "match": True,
                "reason": "old config",
                "cache_fingerprint": old_fingerprint,
            }
        )
    )

    calls = []

    def fake_judge(model_cfg, judge_model, instruction, intercept):
        calls.append(model_cfg)
        return {"match": False, "reason": "reran under new config"}

    out = rescore_one(
        model_cfg=new_cfg,
        judge_model="judge-a",
        run_dir=run_dir,
        force=False,
        rubrics=["strict"],
        judge_funcs={"strict": fake_judge},
    )

    assert calls == [new_cfg]
    assert out["strict"]["match"] is False


def test_cache_fingerprint_excludes_api_keys(tmp_path: Path) -> None:
    """The fingerprint is a non-secret value safe to leave on disk in
    judge.json/judge_llm.json: api_key/api_keys must not affect it, since a
    key rotation with the same endpoint is not a different judge."""
    fp_a = _cache_fingerprint(
        "judge-a", {"api_key": "sk-one", "base_url": "https://x"}, "strict", "i", {}
    )
    fp_b = _cache_fingerprint(
        "judge-a", {"api_key": "sk-two", "base_url": "https://x"}, "strict", "i", {}
    )
    assert fp_a == fp_b


def test_matching_cache_is_still_reused_without_force(tmp_path: Path) -> None:
    """The fingerprint check must not turn every cache into a miss: identical
    judge/config/rubric/instruction/evidence is still a valid reuse."""
    run_dir = _make_run_dir(tmp_path)
    fingerprint = _cache_fingerprint(
        "judge-a",
        {},
        "strict",
        "do the task",
        {"request": {"url": "https://example.test"}},
    )
    (run_dir / "judge.json").write_text(
        json.dumps(
            {"match": True, "reason": "cached", "cache_fingerprint": fingerprint}
        )
    )

    calls = []

    def fake_judge(model_cfg, judge_model, instruction, intercept):
        calls.append(1)
        return {"match": False, "reason": "should not be reached"}

    out = rescore_one(
        model_cfg={},
        judge_model="judge-a",
        run_dir=run_dir,
        force=False,
        rubrics=["strict"],
        judge_funcs={"strict": fake_judge},
    )

    assert calls == []
    assert out["strict"]["reason"] == "cached"


def test_aggregate_batch_flags_mixed_judge_provenance(tmp_path: Path) -> None:
    """If a batch mixes verdicts from two different judges (e.g. --limit left
    some tasks with a stale cache), the rollup must expose that rather than
    silently reporting a single-judge result."""
    batch_dir = tmp_path / "batch-1"
    for name, judge_model in [("run-1", "old-judge"), ("run-2", "new-judge")]:
        run_dir = batch_dir / name
        (run_dir / "data").mkdir(parents=True)
        (run_dir / "run-meta.json").write_text(
            json.dumps({"intercepted": True, "instruction": "do it", "task_id": name})
        )
        (run_dir / "judge.json").write_text(
            json.dumps({"match": True, "reason": "ok", "judge_model": judge_model})
        )

    roll = aggregate_batch(batch_dir, ["strict"])

    assert roll["judge_models_used"] == ["new-judge", "old-judge"]


def test_aggregate_batch_reports_single_judge_when_uniform(tmp_path: Path) -> None:
    batch_dir = tmp_path / "batch-1"
    for name in ["run-1", "run-2"]:
        run_dir = batch_dir / name
        (run_dir / "data").mkdir(parents=True)
        (run_dir / "run-meta.json").write_text(
            json.dumps({"intercepted": True, "instruction": "do it", "task_id": name})
        )
        (run_dir / "judge.json").write_text(
            json.dumps({"match": True, "reason": "ok", "judge_model": "judge-a"})
        )

    roll = aggregate_batch(batch_dir, ["strict"])

    assert roll["judge_models_used"] == ["judge-a"]
