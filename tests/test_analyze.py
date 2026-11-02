"""Tests for the batch error-analysis aggregator (#159, #408)."""

from __future__ import annotations

import json
from pathlib import Path

from clawbench.eval import analyze


def _run(
    root: Path,
    name: str,
    *,
    intercepted: bool,
    reward: float | None = None,
    actions: int = 5,
    claim: bool = False,
    metaclass: str = "daily-life",
    judge_llm: dict[str, object] | None = None,
    judge_strict: dict[str, object] | None = None,
    run_meta_extra: dict[str, object] | None = None,
) -> Path:
    run = root / "model-a" / f"openclaw-{name}-model-a-20260830-120000"
    d = run / "data"
    d.mkdir(parents=True)
    (d / "interception.json").write_text(
        json.dumps({"intercepted": intercepted, "stop_reason": "time_limit_exceeded"})
    )
    (d / "actions.jsonl").write_text("\n".join("{}" for _ in range(actions)))
    (d / "requests.jsonl").write_text("{}\n")
    (d / "agent-messages.jsonl").write_text(
        json.dumps(
            {
                "message": {
                    "role": "assistant" if claim else "user",
                    "content": (
                        "the task is completed successfully"
                        if claim
                        else "report when the task is completed"
                    ),
                }
            }
        )
        + "\n"
    )
    meta: dict[str, object] = {
        "test_case": name,
        "metaclass": metaclass,
        "intercepted": intercepted,
        "result_category": "intercepted" if intercepted else "model_not_intercepted",
        "run_metrics": {"actions": actions},
    }
    if run_meta_extra:
        meta.update(run_meta_extra)
    (run / "run-meta.json").write_text(json.dumps(meta))
    if reward is not None:
        (run / "judge.json").write_text(json.dumps({"match": reward >= 1.0}))
    if judge_strict is not None:
        (run / "judge.json").write_text(json.dumps(judge_strict))
    if judge_llm is not None:
        (run / "judge_llm.json").write_text(json.dumps(judge_llm))
    return run


def test_discover_and_aggregate(tmp_path: Path) -> None:
    _run(tmp_path, "v2-1-daily-life-shopping-etsy", intercepted=True, reward=1.0)
    _run(tmp_path, "v2-2-daily-life-shopping-amazon", intercepted=True, reward=0.0)
    _run(
        tmp_path,
        "v2-3-job-search-hr-indeed",
        intercepted=False,
        reward=0.0,
        actions=0,
        metaclass="job-search",
    )
    stats = analyze.analyze_batch(tmp_path)
    assert stats["n_runs"] == 3
    assert stats["stage1_intercepted"] == 2 and stats["stage1_rate"] == round(2 / 3, 4)
    # 2 judged runs, 1 pass
    assert stats["stage2_judged_of"] == 3 and stats["stage2_pass"] == 1
    assert stats["stage2_overall_pass"] == 1
    assert stats["stage2_overall_rate"] == round(1 / 3, 4)
    # per-category from run metadata
    assert stats["by_category"]["daily-life"]["n"] == 2
    assert stats["by_category"]["job-search"]["n"] == 1


def test_interceptor_false_positive_flagged(tmp_path: Path) -> None:
    # a 0-action run that is (wrongly) intercepted must be counted
    _run(tmp_path, "v2-9-x-y-z", intercepted=True, actions=0)
    stats = analyze.analyze_batch(tmp_path)
    assert stats["interceptor_false_positives"] == 1


def test_self_report_gap(tmp_path: Path) -> None:
    # claimed success but not intercepted / judged-fail
    _run(tmp_path, "v2-1-a-b-c", intercepted=False, claim=True)  # claimed, failed
    _run(
        tmp_path, "v2-2-a-b-c", intercepted=True, reward=1.0, claim=True
    )  # claimed, passed
    stats = analyze.analyze_batch(tmp_path)
    assert stats["self_report_claimed"] == 2
    assert stats["self_report_claimed_but_failed"] == 1


def test_user_text_is_not_a_success_claim(tmp_path: Path) -> None:
    _run(tmp_path, "v2-1-a-b-c", intercepted=False)
    stats = analyze.analyze_batch(tmp_path)
    assert stats["self_report_claimed"] == 0


def test_format_report_and_cli(tmp_path: Path, capsys) -> None:
    _run(tmp_path, "v2-1-daily-life-shopping-etsy", intercepted=True, reward=1.0)
    rc = analyze.main(["--runs-dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Stage-1 intercepted" in out and "Failure taxonomy" in out
    assert "Overall two-stage success" in out


def test_empty_dir_errors(tmp_path: Path) -> None:
    assert analyze.main(["--runs-dir", str(tmp_path)]) == 1


def test_default_lenient_rescore_is_read(tmp_path: Path) -> None:
    run_dir = _run(
        tmp_path,
        "v2-1-daily-life-shopping-etsy",
        intercepted=True,
        judge_llm={
            "match": True,
            "rubric": "lenient",
            "judge_model": "deepseek-v4-pro",
        },
    )
    summary = analyze.run_summary(run_dir)
    assert summary["rubric"] == "lenient"
    assert summary["judged"] is True
    assert summary["two_stage_pass"] is True
    assert summary["judge_model"] == "deepseek-v4-pro"

    stats = analyze.analyze_batch(tmp_path)
    assert stats["rubric"] == "lenient"
    assert stats["judge_model"] == "deepseek-v4-pro"
    assert stats["stage2_judged_of"] == 1
    assert stats["stage2_pass"] == 1
    assert stats["stage2_rate"] == 1.0
    assert stats["stage2_overall_pass"] == 1
    assert stats["stage2_overall_rate"] == 1.0


def test_lenient_rescore_not_masked_by_strict_and_no_silent_substitution(
    tmp_path: Path,
) -> None:
    run1 = _run(
        tmp_path,
        "v2-1-daily-life-shopping-etsy",
        intercepted=True,
        judge_llm={
            "match": True,
            "rubric": "lenient",
            "judge_model": "deepseek-v4-pro",
        },
        run_meta_extra={"judge_match": False, "judge_model": "gpt-4o"},
    )
    # Run 2 has only an older strict/native verdict and no lenient judge_llm.json
    run2 = _run(
        tmp_path,
        "v2-2-daily-life-shopping-amazon",
        intercepted=True,
        judge_strict={"match": True, "judge_model": "gpt-4o"},
        run_meta_extra={"judge_match": True, "judge_model": "gpt-4o"},
    )

    assert analyze.run_summary(run1)["judged"] is True
    assert analyze.run_summary(run1, rubric="strict")["judged"] is False
    assert analyze.run_summary(run2, rubric="lenient")["judged"] is None
    assert analyze.run_summary(run2, rubric="strict")["judged"] is True

    # Batch defaults to lenient when lenient artifacts exist, and must NOT
    # substitute Run 2's strict verdict for its missing lenient verdict.
    lenient_stats = analyze.analyze_batch(tmp_path)
    assert lenient_stats["rubric"] == "lenient"
    assert lenient_stats["stage2_judged_of"] == 1
    assert lenient_stats["stage2_pass"] == 1
    assert lenient_stats["stage2_missing"] == 1
    assert lenient_stats["stage2_unjudged"] == 1
    assert lenient_stats["stage2_rate"] == 1.0
    assert lenient_stats["stage2_overall_pass"] == 1
    assert lenient_stats["stage2_overall_rate"] == 0.5

    strict_stats = analyze.analyze_batch(tmp_path, rubric="strict")
    assert strict_stats["rubric"] == "strict"
    assert strict_stats["stage2_judged_of"] == 2
    assert strict_stats["stage2_pass"] == 1
    assert strict_stats["stage2_fail"] == 1
    assert strict_stats["stage2_rate"] == 0.5
    assert strict_stats["stage2_overall_rate"] == 0.5


def test_overall_two_stage_rate_reported_separately(tmp_path: Path) -> None:
    _run(
        tmp_path,
        "v2-1-daily-life-shopping-etsy",
        intercepted=True,
        judge_strict={"match": True, "judge_model": "deepseek-v4-pro"},
    )
    _run(tmp_path, "v2-2-daily-life-shopping-amazon", intercepted=False)

    stats = analyze.analyze_batch(tmp_path)
    assert stats["n_runs"] == 2
    assert stats["stage1_rate"] == 0.5
    assert stats["stage2_pass"] == 1
    assert stats["stage2_judged_of"] == 1
    assert stats["stage2_rate"] == 1.0
    assert stats["stage2_overall_pass"] == 1
    assert stats["stage2_overall_rate"] == 0.5
    assert stats["two_stage_rate"] == 0.5
    assert stats["stage2_coverage"] == 0.5
    assert stats["stage2_intercepted_coverage"] == 1.0

    report = analyze.format_report(stats)
    assert "**Rubric:** strict (judge: deepseek-v4-pro)" in report
    assert "**Stage-2 judged pass:** 1/1 (100%)" in report
    assert "**Overall two-stage success:** 1/2 (50%)" in report
    assert "**Stage-2 judgment coverage:** 1/2 (50%)" in report


def test_missing_and_inconclusive_judgments_remain_explicit(tmp_path: Path) -> None:
    _run(
        tmp_path,
        "v2-1-daily-life-shopping-etsy",
        intercepted=True,
        judge_llm={"match": None, "reason": "judge_call_failed: timeout"},
    )
    _run(tmp_path, "v2-2-daily-life-shopping-amazon", intercepted=True)

    stats = analyze.analyze_batch(tmp_path, rubric="lenient")
    assert stats["stage2_judged_of"] == 0
    assert stats["stage2_pass"] == 0
    assert stats["stage2_fail"] == 0
    assert stats["stage2_rate"] is None
    assert stats["stage2_overall_rate"] is None
    assert stats["stage2_inconclusive"] == 1
    assert stats["stage2_missing"] == 1
    assert stats["stage2_unjudged"] == 2
    assert stats["failure_taxonomy"].get("judge_inconclusive") == 1


def test_non_intercepted_run_with_stale_positive_verdict_cannot_bypass_stage1(
    tmp_path: Path,
) -> None:
    run_dir = _run(
        tmp_path,
        "v2-1-daily-life-shopping-etsy",
        intercepted=False,
        judge_llm={"match": True, "rubric": "lenient"},
        judge_strict={"match": True, "rubric": "strict"},
        run_meta_extra={"judge_match": True},
    )

    summary = analyze.run_summary(run_dir)
    assert summary["intercepted"] is False
    assert summary["judged"] is None
    assert summary["two_stage_pass"] is False
    assert summary["judge_status"] == "stale_unintercepted"

    stats = analyze.analyze_batch(tmp_path)
    assert stats["stage1_intercepted"] == 0
    assert stats["stage2_judged_of"] == 0
    assert stats["stage2_pass"] == 0
    assert stats["stage2_overall_pass"] == 0
    assert stats["stage2_overall_rate"] == 0.0
    assert stats["stage2_stale_unintercepted"] == 1
