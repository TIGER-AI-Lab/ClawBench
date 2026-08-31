"""Regression tests for issue #299: a judge outage must not be recorded as an
agent failure.

run.py now exits 3, instead of sharing exit 1 with a genuine JUDGE MISMATCH,
when the judge never renders a verdict (match=None). These tests drive
batch.py's run_job() against a mocked subprocess to lock in that exit 3 lands
in its own `judge_inconclusive` bucket, kept out of `failed`/`error`, all the
way into batch-summary.json's totals.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from clawbench.runner import batch
from clawbench.runner.batch import Job, StartupThrottle, run_job, write_summary_json


class _FakeProc:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        self.pid = 99999

    async def communicate(self):
        return b"", None


def _run_one_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, returncode: int
) -> Job:
    batch.shutdown_event = asyncio.Event()
    batch.running_procs.clear()

    async def fake_create_subprocess_exec(*args, **kwargs):
        return _FakeProc(returncode)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    job = Job(model="model-a", case_dir=tmp_path / "case", case_name="case")
    log_dir = tmp_path / "batch-logs"
    log_dir.mkdir()

    asyncio.run(
        run_job(
            job,
            asyncio.Semaphore(1),
            StartupThrottle(0),
            tmp_path,
            log_dir,
            [job],
            0.0,
            no_upload=True,
        )
    )
    return job


@pytest.mark.parametrize(
    "returncode,expected_status",
    [(0, "passed"), (1, "failed"), (3, "judge_inconclusive"), (2, "error")],
)
def test_run_job_maps_exit_code_to_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    returncode: int,
    expected_status: str,
) -> None:
    job = _run_one_job(monkeypatch, tmp_path, returncode)
    assert job.status == expected_status


def test_judge_inconclusive_counted_separately_in_batch_summary_json(
    tmp_path: Path,
) -> None:
    jobs = [
        Job(model="m", case_dir=tmp_path, case_name="passed-case", status="passed"),
        Job(model="m", case_dir=tmp_path, case_name="failed-case", status="failed"),
        Job(
            model="m",
            case_dir=tmp_path,
            case_name="inconclusive-case",
            status="judge_inconclusive",
        ),
    ]

    write_summary_json(jobs, tmp_path, elapsed=1.0, max_concurrent=1, started_at="now")

    data = json.loads((tmp_path / "batch-summary.json").read_text())
    assert data["totals"] == {
        "passed": 1,
        "failed": 1,
        "error": 0,
        "judge_inconclusive": 1,
        "skipped": 0,
    }
