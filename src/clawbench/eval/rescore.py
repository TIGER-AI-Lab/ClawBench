"""Post-hoc LLM judge re-scoring for ClawBench runs.

Walks every completed batch-*/ run, picks tasks where the runner marked
`intercepted=true`, then asks an LLM judge whether the intercepted HTTP
request actually fulfills the natural-language instruction.

Two rubric flavors (controlled by --rubric):
  lenient (default) : src/clawbench/runner/judge_llm.py
                       "no explicit contradiction → match" (matches the
                       public leaderboard at claw-bench.com).
                       Writes <task>/judge_llm.json.
  strict            : src/clawbench/runner/judge.py
                       "ambiguous → mismatch" (original conservative rubric).
                       Writes <task>/judge.json.
  both              : run BOTH judges per task; per-batch summary has both.

Final pass = intercepted AND judge says match.

Outputs:
  <task_dir>/judge_llm.json         per-task verdict (lenient)
  <task_dir>/judge.json             per-task verdict (strict)
  <batch_dir>/rescore-summary.json  per-batch rollup (legacy + new keys)
  eval_results/<batch_name>/        per-batch eval_results dir (default), with:
    per_task.csv                    rows = task_id, cols = intercepted +
                                    match_lenient + match_strict + reasons
    summary.json                    overall %s formatted XX.X%
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml

JUDGE_FILE = {"strict": "judge.json", "lenient": "judge_llm.json"}


def find_run_dirs(root: Path) -> list[Path]:
    return [p.parent for p in root.rglob("run-meta.json")]


def rescore_one(
    model_cfg: dict,
    judge_model: str,
    run_dir: Path,
    force: bool,
    rubrics: list[str],
    judge_funcs: dict,
) -> dict[str, Any]:
    """Run each rubric's judge. Returns {rubric: verdict_dict}."""
    out: dict[str, Any] = {}
    meta_p = run_dir / "run-meta.json"
    try:
        meta = json.loads(meta_p.read_text())
    except Exception:
        return out
    if not meta.get("intercepted"):
        return out
    intercept_p = run_dir / "data" / "interception.json"
    if not intercept_p.exists():
        return out
    try:
        intercept = json.loads(intercept_p.read_text())
    except Exception:
        return out
    instruction = meta.get("instruction", "") or ""
    for rubric in rubrics:
        judge_p = run_dir / JUDGE_FILE[rubric]
        if judge_p.exists() and not force:
            try:
                out[rubric] = json.loads(judge_p.read_text())
                continue
            except Exception:
                pass
        verdict = judge_funcs[rubric](model_cfg, judge_model, instruction, intercept)
        verdict["task_id"] = meta.get("task_id")
        verdict["test_case"] = meta.get("test_case")
        verdict["original_intercepted"] = True
        verdict["rubric"] = rubric
        judge_p.write_text(json.dumps(verdict, indent=2, ensure_ascii=False))
        out[rubric] = verdict
    return out


def aggregate_batch(batch_dir: Path, rubrics: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "batch_dir": str(batch_dir),
        "n_total": 0,
        "n_intercepted": 0,
        "tasks": [],
    }
    for r in rubrics:
        out[f"n_match_{r}"] = 0
        out[f"n_mismatch_{r}"] = 0
        out[f"n_judge_err_{r}"] = 0
    for meta_p in sorted(batch_dir.rglob("run-meta.json")):
        run_dir = meta_p.parent
        try:
            meta = json.loads(meta_p.read_text())
        except Exception:
            continue
        out["n_total"] += 1
        intercepted = bool(meta.get("intercepted"))
        if intercepted:
            out["n_intercepted"] += 1
        task_row: dict[str, Any] = {
            "task_id": meta.get("task_id"),
            "test_case": meta.get("test_case"),
            "intercepted": intercepted,
        }
        for r in rubrics:
            judge_p = run_dir / JUDGE_FILE[r]
            match: Any = None
            reason = ""
            if judge_p.exists():
                try:
                    jd = json.loads(judge_p.read_text())
                    match = jd.get("match")
                    reason = jd.get("reason", "")
                except Exception:
                    pass
            task_row[f"match_{r}"] = match
            task_row[f"reason_{r}"] = reason
            if intercepted:
                if match is True:
                    out[f"n_match_{r}"] += 1
                elif match is False:
                    out[f"n_mismatch_{r}"] += 1
                else:
                    out[f"n_judge_err_{r}"] += 1
        out["tasks"].append(task_row)
    n = out["n_total"]
    out["pass_rate_stage1_only"] = out["n_intercepted"] / n if n else 0
    for r in rubrics:
        out[f"reward_pct_{r}"] = out[f"n_match_{r}"] / n if n else 0
    # Backward-compat aliases for downstream consumers of the old summary schema
    if "strict" in rubrics:
        out["n_judge_match"] = out["n_match_strict"]
        out["n_judge_mismatch"] = out["n_mismatch_strict"]
        out["n_judge_error"] = out["n_judge_err_strict"]
        out["pass_rate_with_judge"] = out["reward_pct_strict"]
    elif "lenient" in rubrics:
        # If only lenient ran, mirror its numbers under legacy keys
        out["n_judge_match"] = out["n_match_lenient"]
        out["n_judge_mismatch"] = out["n_mismatch_lenient"]
        out["n_judge_error"] = out["n_judge_err_lenient"]
        out["pass_rate_with_judge"] = out["reward_pct_lenient"]
    return out


def write_eval_results(
    batch_dir: Path,
    roll: dict[str, Any],
    rubrics: list[str],
    model_label: str,
    eval_dir: Path,
) -> None:
    """Write per-task CSV + summary JSON to eval_results/<batch_name>/."""
    out_dir = eval_dir / batch_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    # Per-task CSV
    csv_p = out_dir / "per_task.csv"
    cols = ["task_id", "test_case", "intercepted"]
    for r in rubrics:
        cols += [f"match_{r}", f"reason_{r}"]
    with csv_p.open("w", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for t in roll["tasks"]:
            w.writerow(t)
    # Summary JSON
    n = roll["n_total"]
    summary = {
        "model": model_label,
        "batch_dir": str(batch_dir),
        "n_total": n,
        "n_intercepted": roll["n_intercepted"],
        "intercepted_pct": f"{100 * roll['n_intercepted'] / n:.1f}%" if n else "0.0%",
    }
    for r in rubrics:
        summary[f"reward_{r}_pct"] = f"{100 * roll[f'reward_pct_{r}']:.1f}%"
        summary[f"match_{r}"] = roll[f"n_match_{r}"]
        summary[f"mismatch_{r}"] = roll[f"n_mismatch_{r}"]
        summary[f"judge_err_{r}"] = roll[f"n_judge_err_{r}"]
    summary["judge_model"] = roll.get("judge_model")
    summary["rubrics"] = rubrics
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )
    print(f"  eval_results written to {out_dir}/")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--sweep-root",
        type=Path,
        default=Path.home() / "work/ClawBench/claw-output/sweep",
    )
    p.add_argument(
        "--judge-model",
        default="deepseek-v4-pro",
        help="Model key in models/models.yaml used to judge "
        "(default deepseek-v4-pro, same model used for our published leaderboard).",
    )
    p.add_argument(
        "--models-yaml",
        type=Path,
        default=Path.home() / "work/ClawBench/models/models.yaml",
    )
    p.add_argument(
        "--rubric",
        choices=["lenient", "strict", "both"],
        default="lenient",
        help="Judge rubric. Default 'lenient' matches the public leaderboard. "
        "'strict' is the conservative original. 'both' runs both.",
    )
    p.add_argument(
        "--eval-results-dir",
        type=Path,
        default=Path("eval_results"),
        help="Where to write per-task CSV + summary JSON (default ./eval_results/)",
    )
    p.add_argument(
        "--no-eval-results",
        action="store_true",
        help="Skip writing the eval_results/ artifact",
    )
    p.add_argument("--workers", type=int, default=4)
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-judge tasks that already have the rubric's judge file",
    )
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--only-batch", type=Path, default=None)
    args = p.parse_args()

    cfg_all = yaml.safe_load(args.models_yaml.read_text())
    if args.judge_model not in cfg_all:
        print(
            f"ERROR: judge model {args.judge_model!r} not in {args.models_yaml}",
            file=sys.stderr,
        )
        return 2
    judge_cfg = dict(cfg_all[args.judge_model])
    if not judge_cfg.get("api_key"):
        print(f"ERROR: judge {args.judge_model!r} has no api_key", file=sys.stderr)
        return 2

    rubrics = [args.rubric] if args.rubric != "both" else ["lenient", "strict"]
    judge_funcs = {}
    if "strict" in rubrics:
        from clawbench.runner.judge import judge_request as judge_strict

        judge_funcs["strict"] = judge_strict
    if "lenient" in rubrics:
        from clawbench.runner.judge_llm import judge_request as judge_lenient

        judge_funcs["lenient"] = judge_lenient

    run_dirs = (
        find_run_dirs(args.only_batch)
        if args.only_batch
        else find_run_dirs(args.sweep_root)
    )

    pending = []
    for rd in run_dirs:
        try:
            m = json.loads((rd / "run-meta.json").read_text())
            if not m.get("intercepted"):
                continue
            needs = any(
                args.force or not (rd / JUDGE_FILE[r]).exists() for r in rubrics
            )
            if needs:
                pending.append(rd)
        except Exception:
            continue
    if args.limit:
        pending = pending[: args.limit]

    print(
        f"discovered {len(run_dirs)} tasks, judging {len(pending)} intercepted "
        f"ones with {args.judge_model} (rubrics: {rubrics})"
    )

    judged = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(
                rescore_one,
                judge_cfg,
                args.judge_model,
                rd,
                args.force,
                rubrics,
                judge_funcs,
            ): rd
            for rd in pending
        }
        for fut in as_completed(futs):
            rd = futs[fut]
            try:
                vmap = fut.result()
                judged += 1
                tags = " ".join(
                    f"{r}={ {True: 'M', False: '.', None: '?'}.get(vmap.get(r, {}).get('match'), '?') }"
                    for r in rubrics
                )
                print(f"  [{judged}/{len(pending)}] {tags} {rd.name[:80]}")
            except Exception as e:
                print(f"  err on {rd}: {e}")

    if args.only_batch:
        batches = [args.only_batch]
    else:
        batches = sorted(
            {
                batch
                for run in run_dirs
                if (
                    batch := next(
                        (p for p in run.parents if p.name.startswith("batch-")), None
                    )
                )
                is not None
            }
        )
    print(f"\nrolling up {len(batches)} batches:")
    for bd in batches:
        try:
            roll = aggregate_batch(bd, rubrics)
        except Exception as e:
            print(f"  err rolling up {bd}: {e}")
            continue
        roll["judge_model"] = args.judge_model
        roll["rubrics"] = rubrics
        (bd / "rescore-summary.json").write_text(
            json.dumps(roll, indent=2, ensure_ascii=False)
        )
        s1 = roll["pass_rate_stage1_only"] * 100
        parts = [f"intercept={roll['n_intercepted']}/{roll['n_total']} ({s1:.1f}%)"]
        for r in rubrics:
            rp = roll[f"reward_pct_{r}"] * 100
            parts.append(f"{r}={roll[f'n_match_{r}']}/{roll['n_total']} ({rp:.1f}%)")
        print(f"  {bd.name}: {' | '.join(parts)}")
        if not args.no_eval_results:
            # Derive model label from batch parent dir (typically the model name)
            model_label = bd.parent.name if bd.parent.name else "model"
            write_eval_results(bd, roll, rubrics, model_label, args.eval_results_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
