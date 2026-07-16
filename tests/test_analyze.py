"""Tests for the batch error-analysis aggregator (#159)."""

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
) -> None:
    d = root / name / "data"
    d.mkdir(parents=True)
    (d / "interception.json").write_text(
        json.dumps({"intercepted": intercepted, "stop_reason": "time_limit_exceeded"})
    )
    (d / "actions.jsonl").write_text("\n".join("{}" for _ in range(actions)))
    (d / "requests.jsonl").write_text("{}\n")
    (d / "agent-messages.jsonl").write_text(
        "the task is completed successfully" if claim else "still working"
    )
    if reward is not None:
        (root / name / "reward.json").write_text(json.dumps({"reward": reward}))


def test_discover_and_aggregate(tmp_path: Path) -> None:
    _run(tmp_path, "v2-1-daily-life-shopping-etsy", intercepted=True, reward=1.0)
    _run(tmp_path, "v2-2-daily-life-shopping-amazon", intercepted=True, reward=0.0)
    _run(
        tmp_path, "v2-3-job-search-hr-indeed", intercepted=False, reward=0.0, actions=0
    )
    stats = analyze.analyze_batch(tmp_path)
    assert stats["n_runs"] == 3
    assert stats["stage1_intercepted"] == 2 and stats["stage1_rate"] == round(2 / 3, 4)
    # 2 judged runs, 1 pass
    assert stats["stage2_judged_of"] == 3 and stats["stage2_pass"] == 1
    # per-category from task-id segments
    assert stats["by_category"]["daily-life-shopping"]["n"] == 2
    assert stats["by_category"]["job-search-hr"]["n"] == 1


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


def test_format_report_and_cli(tmp_path: Path, capsys) -> None:
    _run(tmp_path, "v2-1-daily-life-shopping-etsy", intercepted=True, reward=1.0)
    rc = analyze.main(["--runs-dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Stage-1 intercepted" in out and "Failure taxonomy" in out


def test_empty_dir_errors(tmp_path: Path) -> None:
    assert analyze.main(["--runs-dir", str(tmp_path)]) == 1
