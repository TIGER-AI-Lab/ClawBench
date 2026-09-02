#!/usr/bin/env python3
"""Export a ClawBench batch's rescore-summary.json to an EvalPort ResultSet.

EvalPort (https://github.com/adhabnr-ux/evalport) is a small open interchange
format for portable LLM/agent evaluation results (TestCase/Grader/Result/
ResultSet, JSON Schema + a Python/TS SDK). This script is optional and
additive: it only *reads* files ClawBench already writes after a run
finishes (run-meta.json, the per-run judge verdict, rescore-summary.json)
and writes a new, separate resultset.json alongside them. It does not
change make_run_meta(), the two-stage scoring pipeline, clawbench-rescore,
or any other part of the runner/eval code, and it adds no dependency for
anyone who isn't using it -- see the module-level NOTE below on the one
optional import.

Discussed and scoped in https://github.com/TIGER-AI-Lab/ClawBench/issues/322.
This is the *results* side, complementing the existing *test-case* import
adapters (clawbench-harbor-adapt, clawbench-edgebench-adapt) that run the
other direction: those convert someone else's test-case definitions into
ClawBench's own eval format so ClawBench can run them; this converts a
ClawBench run's own output into a portable results format so it can be
read next to output from any other EvalPort-aware benchmark.

Usage:

    python scripts/export_openeval.py <batch_dir> \\
        --run-id batch-20260902-140000 \\
        --started-at 2026-09-02T14:00:00Z

    # or, via the wrapper:
    scripts/export_openeval.sh <batch_dir>

<batch_dir> is a directory containing rescore-summary.json (written by
`clawbench-rescore` / scripts/rescore.sh) and the run-meta.json files it
was rolled up from. Writes <batch_dir>/resultset.json by default; pass
--out to write elsewhere, or --stdout to print instead of writing a file.

--run-id and --started-at are required: rescore-summary.json records
neither a run id nor a start timestamp for the batch, so there is nothing
honest to default them to. --rubric selects which of
rescore-summary.json's ["rubrics"] to score against (defaults to the
first one that ran, matching clawbench-rescore's own default of
"lenient").

What ClawBench actually emits (verified against the current source in
src/clawbench/runner/run_support/metadata.py, src/clawbench/eval/rescore.py,
and src/clawbench/runner/judge_llm.py -- not just docs/scoring.md, which
describes an idealized/older shape):

* run-meta.json (make_run_meta()) carries test_case, instruction, model,
  harness, intercepted, result_category, failure_category,
  adjusted_eligible, duration_seconds, among other fields. It does NOT
  carry judge_match or final_pass -- docs/scoring.md describes those as
  merged in, but the actual merge point is the rescoring step below, and
  even there no field is literally named final_pass.
* The per-run judge verdict (judge_llm.json for the default "lenient"
  rubric, judge.json for "strict" -- JUDGE_FILE in rescore.py) has a
  `match` key (True/False/None) and a `reason` string (judge_llm.py's
  judge_request()).
* rescore-summary.json (aggregate_batch()) rolls a batch into n_total,
  n_intercepted, judge_model, rubrics, and a tasks[] list of per-task rows
  shaped {"task_id", "test_case", "intercepted", "match_<rubric>",
  "reason_<rubric>"} for each rubric that ran. tasks[] rows do NOT carry
  instruction/model/harness -- those live only in each run's own
  run-meta.json, so this script also walks the batch dir for those files
  to enrich each Result.

Mapping to EvalPort's data model (spec/SPEC.md in the EvalPort repo):

* One ClawBench run -> one EvalPort Result. test_case (or task_id as
  fallback) becomes test_case_id. The two-stage scoring pipeline
  (interception, then LLM judge) becomes two GraderResult entries --
  gr_interception and gr_judge_match -- so the mechanism ClawBench
  actually uses is visible in the result, not collapsed into one opaque
  score. Result.passed is `intercepted AND judge_match is True`, matching
  the `final_pass = intercepted AND judge_match` rule documented in
  docs/scoring.md.
* A batch's rescore-summary.json -> one EvalPort ResultSet.

NOTE on the evalport-sdk import: this script does NOT require
evalport-sdk to run -- the conversion itself is pure stdlib. If
evalport-sdk (`pip install evalport-sdk`) happens to be installed, the
script uses it to validate the ResultSet it produces against the real
EvalPort JSON Schema before writing it out, and to print a clear error if
validation fails; if it isn't installed, the script skips that step and
says so. Either way, nothing in ClawBench's own pyproject.toml dependency
list changes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

OPENEVAL_VERSION_FALLBACK = "1.0.0"

INTERCEPTION_GRADER_ID = "gr_interception"
JUDGE_GRADER_ID = "gr_judge_match"


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def run_to_result(
    run_meta: Dict[str, Any],
    judge: Optional[Dict[str, Any]] = None,
    rubric: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert one ClawBench run into an EvalPort Result dict.

    run_meta is the dict already parsed from that run's run-meta.json (or,
    when only a rescore-summary.json task row is available, a minimal
    stand-in with at least test_case/task_id and intercepted).

    Result.test_case_id prefers run_meta["test_case"]; when that's
    missing, it falls back to run_meta["task_id"] with its "#<run
    suffix>" stripped (ClawBench's real task_id values look like
    "myrecipes/leave-review#0001" -- see make_run_meta() -- where the
    part before "#" is the same stable task identity test_case itself
    carries).

    judge is the dict already parsed from that run's judge verdict file
    (judge_llm.json/judge.json, or the match/reason pulled from a
    rescore-summary.json task row for a given rubric). Pass None when the
    run was never judged (e.g. intercepted was already False, so Stage 2
    never ran per docs/scoring.md).

    Two GraderResult entries are emitted, mirroring ClawBench's real
    two-stage pipeline:

    - gr_interception: score/passed from intercepted alone.
    - gr_judge_match: only present when judge is given. score is
      1.0/0.0/None for match True/False/None (a judge that "could not
      decide" carries a null score and counts as not-passed, exactly like
      ClawBench's own aggregate treats it).

    Result.passed is `intercepted AND match is True`.
    """
    test_case_id = _get(run_meta, "test_case")
    if not test_case_id:
        task_id = _get(run_meta, "task_id")
        if task_id:
            test_case_id = str(task_id).split("#", 1)[0]
    if not test_case_id:
        raise ValueError("run_meta must have a 'test_case' or 'task_id' to become a Result.test_case_id")

    intercepted = bool(_get(run_meta, "intercepted"))

    grader_results: List[Dict[str, Any]] = [
        {
            "grader_id": INTERCEPTION_GRADER_ID,
            "type": "custom",
            "score": 1.0 if intercepted else 0.0,
            "passed": intercepted,
            "reason": "final request matched eval_schema" if intercepted else "final request did not match eval_schema (or agent never reached it)",
            "metadata": {"handler": "clawbench:interception"},
        }
    ]

    judge_match: Optional[bool] = None
    if judge is not None:
        judge_match = _get(judge, "match")
        score = 1.0 if judge_match is True else (0.0 if judge_match is False else None)
        gr: Dict[str, Any] = {
            "grader_id": JUDGE_GRADER_ID,
            "type": "llm_judge",
            "score": score,
            "passed": judge_match is True,
            "metadata": {"handler": "clawbench:llm_judge"},
        }
        reason = _get(judge, "reason")
        if reason:
            gr["reason"] = reason
        judge_model = _get(judge, "judge_model")
        if judge_model:
            gr["metadata"]["judge_model"] = judge_model
        grader_results.append(gr)

    passed = bool(intercepted and judge_match is True)

    metadata: Dict[str, Any] = {}
    for key in ("result_category", "failure_category", "adjusted_eligible", "model", "harness", "task_id"):
        value = _get(run_meta, key)
        if value is not None:
            metadata[key] = value
    if rubric:
        metadata["rubric"] = rubric

    result: Dict[str, Any] = {
        "test_case_id": str(test_case_id),
        "passed": passed,
        "grader_results": grader_results,
    }
    # ClawBench scores an intercepted HTTP request, not a text completion, so
    # there is no honest value for Result.actual_output here; the instruction
    # that was scored against goes under metadata instead.
    instruction = _get(run_meta, "instruction")
    if instruction is not None:
        metadata["instruction"] = instruction
    duration = _get(run_meta, "duration_seconds")
    if isinstance(duration, (int, float)):
        result["duration_ms"] = int(round(duration * 1000))
    if metadata:
        result["metadata"] = metadata
    return result


def to_openeval(
    rescore_summary: Dict[str, Any],
    run_metas: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    run_id: str,
    started_at: str,
    completed_at: Optional[str] = None,
    rubric: Optional[str] = None,
    suite_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert a batch's rescore-summary.json (+ optional run-meta.json map) to an EvalPort ResultSet dict."""
    run_metas = run_metas or {}
    rubrics = rescore_summary.get("rubrics") or ["lenient"]
    if rubric is not None:
        if rubric not in rubrics:
            raise ValueError(
                f"rubric {rubric!r} is not in rescore_summary['rubrics'] "
                f"({rubrics!r}); pass one of those, or omit --rubric to use "
                f"the first one"
            )
        active_rubric = rubric
    else:
        active_rubric = rubrics[0]

    results: List[Dict[str, Any]] = []
    for task_row in rescore_summary.get("tasks", []):
        test_case = task_row.get("test_case")
        base_run_meta = run_metas.get(test_case) if test_case is not None else None
        if base_run_meta is None:
            base_run_meta = {
                "test_case": test_case,
                "task_id": task_row.get("task_id"),
                "intercepted": task_row.get("intercepted"),
            }
        match_key = f"match_{active_rubric}"
        reason_key = f"reason_{active_rubric}"
        judge = None
        # aggregate_batch() writes match_<rubric>/reason_<rubric> for every
        # task row unconditionally (defaulting to match=None, reason="" when
        # there's no judge file) -- but rescore_one() only ever judges a run
        # when it was intercepted; Stage 2 never runs otherwise. So the
        # presence of the key alone doesn't mean a judge actually ran --
        # gate on `intercepted` too, matching that real control flow, rather
        # than emitting a spurious gr_judge_match grader for a run that was
        # never judged.
        if task_row.get("intercepted") and match_key in task_row:
            judge = {
                "match": task_row.get(match_key),
                "reason": task_row.get(reason_key),
                "judge_model": rescore_summary.get("judge_model"),
            }
        results.append(run_to_result(base_run_meta, judge, rubric=active_rubric))

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    n_intercepted = sum(
        1
        for r in results
        for gr in r["grader_results"]
        if gr["grader_id"] == INTERCEPTION_GRADER_ID and gr["passed"]
    )

    batch_dir = rescore_summary.get("batch_dir")
    resolved_suite_id = suite_id or (
        f"clawbench_{batch_dir.rstrip('/').rsplit('/', 1)[-1]}" if batch_dir else "clawbench_batch"
    )

    try:
        from openeval.types import OPENEVAL_VERSION as _V
        version = _V
    except ImportError:
        version = OPENEVAL_VERSION_FALLBACK

    result_set: Dict[str, Any] = {
        "version": version,
        "suite_id": resolved_suite_id,
        "run_id": run_id,
        "started_at": started_at,
        "results": results,
        "runner": {"name": "clawbench", "version": "n/a"},
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": (passed / total) if total else 0.0,
        },
        "metadata": {
            "openeval": {"source": "clawbench"},
            "clawbench_batch_dir": batch_dir,
            "clawbench_rubric": active_rubric,
            "clawbench_n_intercepted": n_intercepted,
        },
    }
    if completed_at is not None:
        result_set["completed_at"] = completed_at
    return result_set


def _load_run_metas(batch_dir: Path) -> Dict[str, Dict[str, Any]]:
    run_metas: Dict[str, Dict[str, Any]] = {}
    for meta_path in batch_dir.rglob("run-meta.json"):
        try:
            meta = json.loads(meta_path.read_text())
        except Exception as exc:  # noqa: BLE001 - best-effort enrichment, never fatal
            print(f"warning: could not parse {meta_path}: {exc}", file=sys.stderr)
            continue
        test_case = meta.get("test_case")
        if test_case:
            run_metas[test_case] = meta
    return run_metas


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("batch_dir", type=Path, help="Batch directory containing rescore-summary.json")
    parser.add_argument("--run-id", required=True, help="Run id for the resulting ResultSet (e.g. the batch directory name)")
    parser.add_argument("--started-at", required=True, help="ISO-8601 start timestamp for the batch (rescore-summary.json doesn't record one)")
    parser.add_argument("--completed-at", default=None, help="Optional ISO-8601 completion timestamp")
    parser.add_argument("--rubric", default=None, help="Which rubric to score against (default: the first one in rescore-summary.json's rubrics)")
    parser.add_argument("--suite-id", default=None, help="Optional suite id override (default: derived from the batch directory name)")
    parser.add_argument("--out", type=Path, default=None, help="Output path (default: <batch_dir>/resultset.json)")
    parser.add_argument("--stdout", action="store_true", help="Print the ResultSet to stdout instead of writing a file")
    parser.add_argument("--no-validate", action="store_true", help="Skip validation even if evalport-sdk is installed")
    args = parser.parse_args(argv)

    summary_path = args.batch_dir / "rescore-summary.json"
    if not summary_path.exists():
        print(f"error: {summary_path} not found -- run clawbench-rescore / scripts/rescore.sh on this batch first", file=sys.stderr)
        return 2
    rescore_summary = json.loads(summary_path.read_text())

    run_metas = _load_run_metas(args.batch_dir)

    try:
        result_set = to_openeval(
            rescore_summary,
            run_metas,
            run_id=args.run_id,
            started_at=args.started_at,
            completed_at=args.completed_at,
            rubric=args.rubric,
            suite_id=args.suite_id,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not args.no_validate:
        try:
            from openeval.validate import validate_result_set
        except ImportError:
            print("note: evalport-sdk not installed, skipping schema validation (pip install evalport-sdk to enable)", file=sys.stderr)
        else:
            validation = validate_result_set(result_set)
            if not validation.valid:
                print("error: produced ResultSet failed EvalPort schema validation:", file=sys.stderr)
                for err in validation.errors:
                    print(f"  - {err}", file=sys.stderr)
                return 1
            print(f"validated OK against evalport-sdk's real schema ({len(result_set['results'])} results)", file=sys.stderr)

    payload = json.dumps(result_set, indent=2, ensure_ascii=False)
    if args.stdout:
        print(payload)
    else:
        out_path = args.out or (args.batch_dir / "resultset.json")
        out_path.write_text(payload)
        print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
