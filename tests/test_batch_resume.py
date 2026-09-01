"""--resume must re-run what never finished, and must not destroy the summary.

Resume used to decide completion from `batch-logs/<case>-<model>.log`. That
file is created when a job *starts*, so every job killed mid-run -- the network
blip, the OOM, the wedged container -- looked complete and was skipped, which
inverts the flag's whole purpose. The rewritten batch-summary.json then recorded
every previously finished job as `status: "skipped", duration_seconds: 0`,
destroying the tallies that downstream stats and the HF upload read.

run-meta.json is the authoritative record: run.py writes it for any run that got
far enough to have an outcome, failures included.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawbench.runner.batch import (
    Job,
    apply_resume,
    is_infra_class_failure,
    load_recorded_runs,
    recorded_outcome,
    write_summary_json,
)


def _job(case: str, model: str) -> Job:
    return Job(model=model, case_dir=Path("test-cases/v2") / case, case_name=case)


def _safe(model: str) -> str:
    return model.replace("/", "--").replace(":", "--")


def _record_run(
    base: Path,
    case: str,
    model: str,
    *,
    intercepted: bool = False,
    failure_category: str | None = None,
    infra_failure: bool = False,
    duration: int = 90,
    stamp: str = "20260101-000000",
) -> Path:
    """Write a run-meta.json where a real run would put one."""
    run_dir = base / _safe(model) / f"claw-code-{case}-{_safe(model)}-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run-meta.json").write_text(
        json.dumps(
            {
                "test_case": case,
                "model": model,
                "timestamp": stamp,
                "duration_seconds": duration,
                "intercepted": intercepted,
                "result_category": "intercepted" if intercepted else failure_category,
                "failure_category": failure_category,
                "infra_failure": infra_failure,
            }
        )
    )
    return run_dir


def _start_log(base: Path, case: str, model: str) -> Path:
    """The log batch.py opens when a job starts, before it has any outcome."""
    log_dir = base / "batch-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{case}-{_safe(model)}.log"
    path.write_text("[START] ...\n")
    return path


# --- the regression -----------------------------------------------------------


def test_a_job_that_started_but_never_finished_is_run_again(tmp_path: Path) -> None:
    """The bug: a log file means "started", not "done". A job killed before it
    could write run-meta.json is exactly the job --resume exists to re-run."""
    _start_log(tmp_path, "002-food", "glm-5.1")
    jobs = [_job("002-food", "glm-5.1")]

    carried, retried = apply_resume(jobs, tmp_path)

    assert (carried, retried) == (0, 0)
    assert jobs[0].status == "pending"
    assert jobs[0].resumed is False


def test_a_finished_job_is_not_run_again(tmp_path: Path) -> None:
    _record_run(tmp_path, "002-food", "glm-5.1", intercepted=True)
    jobs = [_job("002-food", "glm-5.1")]

    carried, _ = apply_resume(jobs, tmp_path)

    assert carried == 1
    assert jobs[0].resumed is True


def test_resume_keeps_the_recorded_outcome_not_a_skipped_row(tmp_path: Path) -> None:
    """Second half of the bug: the rewritten summary replaced real results with
    `skipped` / 0s, so a resumed batch reported nothing it had actually done."""
    _record_run(tmp_path, "002-food", "glm-5.1", intercepted=True, duration=214)
    jobs = [_job("002-food", "glm-5.1")]

    apply_resume(jobs, tmp_path)

    assert jobs[0].status == "passed"
    assert jobs[0].duration == 214


def test_the_written_summary_preserves_carried_over_totals(tmp_path: Path) -> None:
    _record_run(tmp_path, "002-food", "glm-5.1", intercepted=True, duration=214)
    _record_run(
        tmp_path, "003-mail", "glm-5.1", failure_category="model_not_intercepted"
    )
    jobs = [_job("002-food", "glm-5.1"), _job("003-mail", "glm-5.1")]
    apply_resume(jobs, tmp_path)

    write_summary_json(jobs, tmp_path, 12.0, 2, "2026-01-01T00:00:00+00:00")
    summary = json.loads((tmp_path / "batch-summary.json").read_text())

    assert summary["totals"] == {"passed": 1, "failed": 1, "error": 0, "skipped": 0}
    assert [j["duration_seconds"] for j in summary["jobs"]] == [214, 90]
    assert all(j["resumed"] for j in summary["jobs"])


# --- outcome mapping ----------------------------------------------------------


@pytest.mark.parametrize(
    "meta, expected",
    [
        ({"intercepted": True}, "passed"),
        ({"intercepted": False, "failure_category": "model_not_intercepted"}, "failed"),
        ({"intercepted": False, "infra_failure": True}, "error"),
        ({"intercepted": False, "failure_category": "api_or_credit"}, "error"),
    ],
)
def test_recorded_outcome_maps_a_run_to_a_batch_status(
    meta: dict, expected: str
) -> None:
    assert recorded_outcome(meta)[0] == expected


def test_a_missing_or_unparsable_duration_does_not_crash_resume() -> None:
    assert recorded_outcome({"intercepted": True})[1] == 0.0
    assert recorded_outcome({"intercepted": True, "duration_seconds": None})[1] == 0.0
    assert recorded_outcome({"intercepted": True, "duration_seconds": "?"})[1] == 0.0


def test_infra_class_uses_the_scorers_own_vocabulary() -> None:
    """These are the categories excluded from adjusted scoring, so the run
    carries no signal about the model and re-running it is the only recourse."""
    for category in (
        "infra_failure",
        "api_or_credit",
        "task_data",
        "build_instruction",
    ):
        assert is_infra_class_failure({"failure_category": category}), category
    assert not is_infra_class_failure({"failure_category": "model_not_intercepted"})


# --- --retry-failed -----------------------------------------------------------


def test_retry_failed_reruns_infra_failures(tmp_path: Path) -> None:
    _record_run(
        tmp_path,
        "002-food",
        "glm-5.1",
        infra_failure=True,
        failure_category="infra_failure",
    )
    jobs = [_job("002-food", "glm-5.1")]

    carried, retried = apply_resume(jobs, tmp_path, retry_failed=True)

    assert (carried, retried) == (0, 1)
    assert jobs[0].status == "pending"


def test_retry_failed_keeps_genuine_model_failures(tmp_path: Path) -> None:
    """The model was asked and it failed. Re-running buys the same answer."""
    _record_run(
        tmp_path, "002-food", "glm-5.1", failure_category="model_not_intercepted"
    )
    jobs = [_job("002-food", "glm-5.1")]

    carried, retried = apply_resume(jobs, tmp_path, retry_failed=True)

    assert (carried, retried) == (1, 0)
    assert jobs[0].status == "failed"


def test_without_the_flag_a_failed_run_is_left_alone(tmp_path: Path) -> None:
    _record_run(
        tmp_path,
        "002-food",
        "glm-5.1",
        infra_failure=True,
        failure_category="infra_failure",
    )
    jobs = [_job("002-food", "glm-5.1")]

    carried, retried = apply_resume(jobs, tmp_path)

    assert (carried, retried) == (1, 0)
    assert jobs[0].status == "error"


# --- reading the recorded runs ------------------------------------------------


def test_the_newest_run_for_a_pair_wins(tmp_path: Path) -> None:
    """Resuming repeatedly leaves several run dirs for one case x model."""
    _record_run(
        tmp_path,
        "002-food",
        "glm-5.1",
        stamp="20260101-000000",
        failure_category="infra_failure",
        infra_failure=True,
    )
    _record_run(
        tmp_path, "002-food", "glm-5.1", stamp="20260102-000000", intercepted=True
    )

    recorded = load_recorded_runs(tmp_path)

    assert recorded[("002-food", "glm-5.1")]["intercepted"] is True


def test_a_truncated_run_meta_is_not_guessed_at(tmp_path: Path) -> None:
    """#312/#325 showed run-meta.json can be truncated. An unreadable outcome is
    an unknown outcome, so the job runs again rather than being invented."""
    run_dir = _record_run(tmp_path, "002-food", "glm-5.1", intercepted=True)
    (run_dir / "run-meta.json").write_text('{"test_case": "002-food", "mod')
    jobs = [_job("002-food", "glm-5.1")]

    carried, _ = apply_resume(jobs, tmp_path)

    assert carried == 0
    assert jobs[0].status == "pending"


def test_a_model_name_with_a_slash_still_matches_its_job(tmp_path: Path) -> None:
    """Run dirs sanitize `/` to `--`, so the match keys off the metadata."""
    _record_run(tmp_path, "002-food", "anthropic/claude-sonnet-4-6", intercepted=True)
    jobs = [_job("002-food", "anthropic/claude-sonnet-4-6")]

    carried, _ = apply_resume(jobs, tmp_path)

    assert carried == 1
    assert jobs[0].status == "passed"


def test_an_empty_or_missing_output_dir_reads_as_nothing_done(tmp_path: Path) -> None:
    assert load_recorded_runs(tmp_path) == {}
    assert load_recorded_runs(tmp_path / "nope") == {}
