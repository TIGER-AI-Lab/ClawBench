from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "export_openeval.py"


def _load_module():
    """Import scripts/export_openeval.py directly (it's a standalone script, not a package)."""
    spec = importlib.util.spec_from_file_location("export_openeval", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_meta(
    test_case: str = "myrecipes/leave-review",
    task_id: str = "myrecipes/leave-review#0001",
    intercepted: bool = True,
    result_category: str = "success",
) -> dict:
    return {
        "test_case": test_case,
        "task_id": task_id,
        "instruction": "Leave a 5-star review for the lasagna recipe.",
        "model": "gpt-5",
        "harness": "claude-code",
        "intercepted": intercepted,
        "result_category": result_category,
        "failure_category": None,
        "adjusted_eligible": True,
        "duration_seconds": 42.3,
    }


def _judge_llm(match: bool | None = True, reason: str = "matches instruction") -> dict:
    return {
        "match": match,
        "reason": reason,
        "judge_model": "deepseek-v4-pro",
        "raw": '{"match": true, "reason": "matches instruction"}',
        "rubric": "lenient",
    }


# --- run_to_result() ---


def test_run_to_result_intercepted_and_matched():
    module = _load_module()
    run_meta = _run_meta()
    judge = _judge_llm(match=True)

    result = module.run_to_result(run_meta, judge, rubric="lenient")

    assert result["test_case_id"] == "myrecipes/leave-review"
    assert result["passed"] is True
    graders = {g["grader_id"]: g for g in result["grader_results"]}
    assert graders["gr_interception"]["passed"] is True
    assert graders["gr_interception"]["score"] == 1.0
    assert graders["gr_judge_match"]["passed"] is True
    assert graders["gr_judge_match"]["score"] == 1.0
    assert graders["gr_judge_match"]["reason"] == "matches instruction"
    assert result["metadata"]["result_category"] == "success"
    assert result["metadata"]["instruction"] == run_meta["instruction"]
    assert result["duration_ms"] == 42300


def test_run_to_result_never_intercepted_has_no_judge_grader():
    module = _load_module()
    run_meta = _run_meta(intercepted=False, result_category="agent_gave_up")

    result = module.run_to_result(run_meta, judge=None)

    assert result["passed"] is False
    assert len(result["grader_results"]) == 1
    assert result["grader_results"][0]["grader_id"] == "gr_interception"
    assert result["grader_results"][0]["passed"] is False


def test_run_to_result_judge_could_not_decide_is_not_passed_with_null_score():
    module = _load_module()
    run_meta = _run_meta()
    judge = _judge_llm(match=None, reason="unparseable")

    result = module.run_to_result(run_meta, judge)

    assert result["passed"] is False
    judge_gr = next(g for g in result["grader_results"] if g["grader_id"] == "gr_judge_match")
    assert judge_gr["score"] is None
    assert judge_gr["passed"] is False


def test_run_to_result_falls_back_to_task_id_when_test_case_missing():
    module = _load_module()
    run_meta = {"task_id": "myrecipes/leave-review#0007", "intercepted": True}

    result = module.run_to_result(run_meta)

    assert result["test_case_id"] == "myrecipes/leave-review"


def test_run_to_result_raises_without_test_case_or_task_id():
    module = _load_module()
    import pytest

    with pytest.raises(ValueError):
        module.run_to_result({"intercepted": True})


# --- to_openeval() ---


def _rescore_summary(rubrics=("lenient",), judge_model="deepseek-v4-pro") -> dict:
    return {
        "batch_dir": "/work/claw-output/sweep/gpt-5/batch-20260902-140000",
        "n_total": 2,
        "n_intercepted": 2,
        "judge_model": judge_model,
        "rubrics": list(rubrics),
        "tasks": [
            {
                "task_id": "myrecipes/leave-review#0001",
                "test_case": "myrecipes/leave-review",
                "intercepted": True,
                "match_lenient": True,
                "reason_lenient": "matches instruction",
            },
            {
                "task_id": "citylibrary/reserve-book#0002",
                "test_case": "citylibrary/reserve-book",
                "intercepted": True,
                "match_lenient": False,
                "reason_lenient": "wrong book title",
            },
        ],
    }


def test_to_openeval_builds_valid_result_set_and_summary():
    module = _load_module()
    summary = _rescore_summary()
    run_metas = {"myrecipes/leave-review": _run_meta()}

    result_set = module.to_openeval(
        summary,
        run_metas,
        run_id="batch-20260902-140000",
        started_at="2026-09-02T14:00:00Z",
    )

    assert result_set["run_id"] == "batch-20260902-140000"
    assert result_set["suite_id"] == "clawbench_batch-20260902-140000"
    assert len(result_set["results"]) == 2
    assert result_set["summary"]["total"] == 2
    assert result_set["summary"]["passed"] == 1
    assert result_set["summary"]["failed"] == 1
    assert result_set["metadata"]["clawbench_rubric"] == "lenient"
    assert result_set["metadata"]["clawbench_n_intercepted"] == 2

    # Enriched result carries instruction/model/harness from run_metas;
    # the un-enriched one only has what the task row itself carries.
    enriched = next(r for r in result_set["results"] if r["test_case_id"] == "myrecipes/leave-review")
    assert enriched["metadata"]["instruction"] == run_metas["myrecipes/leave-review"]["instruction"]
    bare = next(r for r in result_set["results"] if r["test_case_id"] == "citylibrary/reserve-book")
    assert "instruction" not in bare.get("metadata", {})

    from openeval.validate import validate_result_set

    validation = validate_result_set(result_set)
    assert validation.valid, validation.errors


def test_to_openeval_rejects_unknown_rubric():
    module = _load_module()
    import pytest

    with pytest.raises(ValueError):
        module.to_openeval(
            _rescore_summary(rubrics=("lenient",)),
            run_id="r1",
            started_at="2026-09-02T14:00:00Z",
            rubric="strict",
        )


def test_to_openeval_gates_judge_grader_on_intercepted():
    """A task row can carry a stale match_<rubric> key from an older rescore
    even when intercepted is False (Stage 2 never actually ran for it) --
    to_openeval() must not fabricate a judge grader for that row."""
    module = _load_module()
    summary = _rescore_summary()
    summary["tasks"][1]["intercepted"] = False
    # aggregate_batch() still writes match_<rubric>/reason_<rubric> unconditionally.
    summary["tasks"][1]["match_lenient"] = None
    summary["tasks"][1]["reason_lenient"] = ""

    result_set = module.to_openeval(summary, run_id="r1", started_at="2026-09-02T14:00:00Z")

    never_intercepted = next(r for r in result_set["results"] if r["test_case_id"] == "citylibrary/reserve-book")
    assert len(never_intercepted["grader_results"]) == 1
    assert never_intercepted["grader_results"][0]["grader_id"] == "gr_interception"


# --- CLI ---


def test_cli_writes_resultset_json_and_validates(tmp_path: Path):
    batch_dir = tmp_path / "batch-20260902-140000"
    run_dir = batch_dir / "myrecipes-leave-review"
    run_dir.mkdir(parents=True)
    (run_dir / "run-meta.json").write_text(json.dumps(_run_meta()))
    (batch_dir / "rescore-summary.json").write_text(json.dumps(_rescore_summary()))

    env = os.environ.copy()
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            str(batch_dir),
            "--run-id",
            "batch-20260902-140000",
            "--started-at",
            "2026-09-02T14:00:00Z",
        ],
        capture_output=True,
        env=env,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    out_path = batch_dir / "resultset.json"
    assert out_path.is_file()
    result_set = json.loads(out_path.read_text())
    assert result_set["run_id"] == "batch-20260902-140000"
    assert len(result_set["results"]) == 2
    # The enriched result should have picked up instruction/model/harness
    # from myrecipes-leave-review/run-meta.json found by rglob.
    enriched = next(r for r in result_set["results"] if r["test_case_id"] == "myrecipes/leave-review")
    assert enriched["metadata"]["model"] == "gpt-5"


def test_cli_errors_cleanly_when_rescore_summary_missing(tmp_path: Path):
    batch_dir = tmp_path / "empty-batch"
    batch_dir.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            str(batch_dir),
            "--run-id",
            "r1",
            "--started-at",
            "2026-09-02T14:00:00Z",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 2
    assert "rescore-summary.json" in result.stderr


def test_cli_help_smoke():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "usage" in (result.stdout + result.stderr).lower()
