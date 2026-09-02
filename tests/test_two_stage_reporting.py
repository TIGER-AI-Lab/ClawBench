"""Both scoring stages are reported together (#243)."""

from __future__ import annotations

import json
from pathlib import Path

from clawbench.runner import batch


def _write_run(
    base: Path,
    model: str,
    case: str,
    *,
    intercepted: bool,
    judge_match: bool | None | str = "absent",
    judge_model: str | None = "deepseek-v4-pro",
) -> None:
    run_dir = base / model / case
    (run_dir / "data").mkdir(parents=True)
    meta: dict = {
        "test_case": case,
        "model": model,
        "intercepted": intercepted,
        "duration_seconds": 300,
        "run_flags": {"judge": judge_model},
    }
    if judge_match != "absent":
        meta["judge_match"] = judge_match
    (run_dir / "run-meta.json").write_text(json.dumps(meta))


def _batch_with_known_stage_split(tmp_path: Path) -> Path:
    """Four runs: 3 intercepted, 1 of those judged a match, 1 unjudged."""
    base = tmp_path / "test-output"
    _write_run(base, "model-a", "case-1", intercepted=True, judge_match=True)
    _write_run(base, "model-a", "case-2", intercepted=True, judge_match=False)
    _write_run(base, "model-a", "case-3", intercepted=True, judge_match=None)
    _write_run(base, "model-a", "case-4", intercepted=False, judge_match=False)
    return base


def test_stage_totals_separates_interception_from_judged(tmp_path: Path) -> None:
    rows = batch.collect_run_rows(_batch_with_known_stage_split(tmp_path))
    totals = batch.stage_totals(rows)

    assert totals["runs"] == 4
    assert totals["stage1_intercepted"] == 3
    assert totals["stage1_rate"] == 0.75
    assert totals["stage2_judged_match"] == 1
    assert totals["stage2_rate"] == 0.25
    # 1 of 3 intercepted runs survived the judge: the "right request, wrong
    # intent" gap this issue is about.
    assert totals["stage1_precision"] == round(1 / 3, 4)
    assert totals["judge_models"] == ["deepseek-v4-pro"]
    assert totals["judge_ran"] is True


def test_a_failed_judge_call_is_not_a_stage_2_failure(tmp_path: Path) -> None:
    """judge_match=None means no verdict, which is not the same as 'no match'."""
    rows = batch.collect_run_rows(_batch_with_known_stage_split(tmp_path))
    totals = batch.stage_totals(rows)

    assert totals["stage2_unjudged"] == 1
    assert totals["stage2_judged_match"] == 1


def test_no_judge_run_reports_the_absence_instead_of_a_stage_1_headline(
    tmp_path: Path,
) -> None:
    base = tmp_path / "test-output"
    _write_run(base, "model-a", "case-1", intercepted=True, judge_model=None)
    _write_run(base, "model-a", "case-2", intercepted=False, judge_model=None)

    totals = batch.stage_totals(batch.collect_run_rows(base))
    line = batch.format_stage_totals(totals)

    assert totals["judge_ran"] is False
    assert totals["stage2_rate"] is None
    assert "stage 1 (intercepted): 1/2" in line
    assert "not run" in line
    # The interception count must never be the only number on the line.
    assert "stage 2" in line


def test_summary_line_carries_both_stages_and_the_judge_model(
    tmp_path: Path,
) -> None:
    totals = batch.stage_totals(
        batch.collect_run_rows(_batch_with_known_stage_split(tmp_path))
    )
    line = batch.format_stage_totals(totals)

    assert "stage 1 (intercepted): 3/4 (75%)" in line
    assert "stage 2 (judged, deepseek-v4-pro): 1/4 (25%)" in line
    assert "stage-1 precision: 33%" in line
    assert "1 awaiting a verdict" in line


def test_batch_summary_json_carries_both_stages(tmp_path: Path) -> None:
    base = _batch_with_known_stage_split(tmp_path)
    jobs = [
        batch.Job(case_dir=Path("case-1"), case_name="case-1", model="model-a"),
    ]
    jobs[0].status = "passed"

    batch.write_summary_json(
        jobs,
        base,
        elapsed=12.0,
        max_concurrent=2,
        started_at="2026-01-01T00:00:00+00:00",
    )

    summary = json.loads((base / "batch-summary.json").read_text())
    assert summary["stages"]["stage1_intercepted"] == 3
    assert summary["stages"]["stage2_judged_match"] == 1
    assert summary["stages"]["judge_models"] == ["deepseek-v4-pro"]
    # The pre-existing job-status totals are unchanged.
    assert summary["totals"]["passed"] == 1


def test_stage_totals_on_an_empty_batch_does_not_divide_by_zero() -> None:
    totals = batch.stage_totals([])

    assert totals["runs"] == 0
    assert totals["judge_ran"] is False
    assert totals["stage1_rate"] is None
    assert totals["stage2_rate"] is None
    assert totals["stage1_precision"] is None
