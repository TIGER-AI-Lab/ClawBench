"""A judge outage is a missing verdict, not a failed task.

judge.py returns match=None when the call fails after retries -- HTTP 402, a
timeout, an unsupported api_type. run.py exited 1 for that, batch.py counts
exit 1 as "failed", and so a judge account hitting 402 mid-sweep recorded whole
batches as agent failures, silently deflating reward. The run itself was fine;
only stage 2 was missing.
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from clawbench.eval import rescore
from clawbench.runner.batch import JOB_STATUSES, Job, write_summary_json
from clawbench.runner.run_support.results import (
    JUDGE_INCONCLUSIVE_EXIT,
    is_judge_inconclusive,
)

RUN_PY = Path(__file__).resolve().parents[1] / "src" / "clawbench" / "runner" / "run.py"


# --- what counts as inconclusive ---------------------------------------------


def test_a_judge_outage_on_an_intercepted_run_is_inconclusive() -> None:
    assert is_judge_inconclusive({"intercepted": True, "judge_match": None})


@pytest.mark.parametrize(
    "meta",
    [
        {"intercepted": True, "judge_match": True},
        {"intercepted": True, "judge_match": False},
    ],
)
def test_a_real_verdict_is_not_inconclusive(meta: dict) -> None:
    """A judge that said "no" answered the question. Only a judge that could
    not answer leaves the run outstanding."""
    assert not is_judge_inconclusive(meta)


def test_no_judge_is_not_inconclusive() -> None:
    """--no-judge attempted nothing, so nothing is outstanding; without this the
    whole --no-judge corpus would look like it needed re-judging."""
    assert not is_judge_inconclusive({"intercepted": True})


def test_a_run_that_never_intercepted_is_not_inconclusive() -> None:
    """Stage 1 already decided it. Re-judging cannot change that."""
    assert not is_judge_inconclusive({"intercepted": False, "judge_match": None})


# --- run.py's exit code -------------------------------------------------------


def test_the_exit_code_is_distinct_from_agent_failure() -> None:
    assert JUDGE_INCONCLUSIVE_EXIT not in (0, 1, 2)


def test_run_exits_the_distinct_code_only_when_the_verdict_is_missing() -> None:
    """The branch already printed MISMATCH vs INCONCLUSIVE but exited 1 for
    both. Read from source rather than imported: run.py pulls in
    run_support.config, which probes for a container engine at import time and
    exits when none is installed (#315)."""
    src = RUN_PY.read_text(encoding="utf-8")

    assert "sys.exit(1 if verdict is False else JUDGE_INCONCLUSIVE_EXIT)" in src
    assert "JUDGE_INCONCLUSIVE_EXIT," in src  # imported, not redefined


# --- batch.py's accounting ----------------------------------------------------


def test_unjudged_is_a_status_of_its_own() -> None:
    assert "unjudged" in JOB_STATUSES
    for expected in ("passed", "failed", "error", "skipped"):
        assert expected in JOB_STATUSES, expected


def test_the_summary_counts_unjudged_apart_from_failed(tmp_path: Path) -> None:
    """The reported bug: "N runs unjudged" was indistinguishable from "N runs
    the model failed" in batch-summary.json."""
    jobs = [
        Job(model="glm-5.1", case_dir=Path("c"), case_name="a", status="passed"),
        Job(model="glm-5.1", case_dir=Path("c"), case_name="b", status="failed"),
        Job(model="glm-5.1", case_dir=Path("c"), case_name="c", status="unjudged"),
        Job(model="glm-5.1", case_dir=Path("c"), case_name="d", status="unjudged"),
    ]

    write_summary_json(jobs, tmp_path, 1.0, 2, "2026-01-01T00:00:00+00:00")
    totals = json.loads((tmp_path / "batch-summary.json").read_text())["totals"]

    assert totals["unjudged"] == 2
    assert totals["failed"] == 1
    assert totals["passed"] == 1


def test_batch_maps_the_exit_code_to_unjudged() -> None:
    """Guard the wiring between the two modules: run.py's code and batch.py's
    status have to stay in agreement or the count silently reverts to failed."""
    from clawbench.runner import batch as batch_mod

    src = inspect.getsource(batch_mod.run_job)

    assert "elif proc.returncode == JUDGE_INCONCLUSIVE_EXIT:" in src
    assert 'job.status = "unjudged"' in src


# --- rescore --only-unjudged --------------------------------------------------


def _write_run(base: Path, name: str, meta: dict) -> Path:
    run_dir = base / name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run-meta.json").write_text(json.dumps(meta))
    return run_dir


def test_only_unjudged_selects_exactly_the_runs_missing_a_verdict(
    tmp_path: Path,
) -> None:
    outage = _write_run(tmp_path, "outage", {"intercepted": True, "judge_match": None})
    _write_run(tmp_path, "matched", {"intercepted": True, "judge_match": True})
    _write_run(tmp_path, "mismatch", {"intercepted": True, "judge_match": False})
    _write_run(tmp_path, "not-intercepted", {"intercepted": False})

    assert rescore.find_run_dirs(tmp_path, only_unjudged=True) == [outage]


def test_without_the_flag_every_run_is_still_returned(tmp_path: Path) -> None:
    _write_run(tmp_path, "outage", {"intercepted": True, "judge_match": None})
    _write_run(tmp_path, "matched", {"intercepted": True, "judge_match": True})

    assert len(rescore.find_run_dirs(tmp_path)) == 2


def test_an_unreadable_run_meta_is_skipped_not_crashed_on(tmp_path: Path) -> None:
    bad = _write_run(tmp_path, "bad", {"intercepted": True, "judge_match": None})
    (bad / "run-meta.json").write_text('{"intercepted": tr')

    assert rescore.find_run_dirs(tmp_path, only_unjudged=True) == []


def test_rescore_still_does_not_need_a_container_engine() -> None:
    """rescore imports run_support.results now. That module must stay free of
    the import-time engine probe, or a post-hoc scoring tool starts requiring
    Docker. Imported in a subprocess with an empty PATH so the probe would
    actually fire if it were reachable."""
    result = subprocess.run(
        [sys.executable, "-c", "import clawbench.eval.rescore"],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": "",
            "CONTAINER_ENGINE": "",
            "PYTHONPATH": str(RUN_PY.parents[2]),
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "not found on PATH" not in result.stdout
