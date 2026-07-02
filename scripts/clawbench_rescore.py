"""Post-hoc LLM judge re-scoring for ClawBench runs.

Walks every completed batch-*/ run, picks tasks where the runner marked
`intercepted=true`, then asks an LLM judge whether the intercepted HTTP
request actually fulfills the natural-language instruction.
Final pass = intercepted AND judge says match.

Per-task output: <task_dir>/judge.json
Per-batch rollup: <batch_dir>/rescore-summary.json

Uses src/clawbench/runner/judge.py — same code path as the inline judge.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Locate the package
PKG = Path(__file__).resolve().parent.parent / "src"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

import yaml

from clawbench.runner.judge import judge_request


def find_run_dirs(root: Path) -> list[Path]:
    return [p.parent for p in root.rglob("run-meta.json")]


def rescore_one(model_cfg: dict, judge_model: str, run_dir: Path, force: bool) -> dict[str, Any] | None:
    meta_p = run_dir / "run-meta.json"
    judge_p = run_dir / "judge.json"
    if judge_p.exists() and not force:
        return json.loads(judge_p.read_text())
    try:
        meta = json.loads(meta_p.read_text())
    except Exception:
        return None
    if not meta.get("intercepted"):
        return None
    intercept_p = run_dir / "data" / "interception.json"
    if not intercept_p.exists():
        return None
    try:
        intercept = json.loads(intercept_p.read_text())
    except Exception:
        return None
    instruction = meta.get("instruction", "") or ""
    verdict = judge_request(model_cfg, judge_model, instruction, intercept)
    verdict["task_id"] = meta.get("task_id")
    verdict["test_case"] = meta.get("test_case")
    verdict["original_intercepted"] = True
    judge_p.write_text(json.dumps(verdict, indent=2, ensure_ascii=False))
    return verdict


def aggregate_batch(batch_dir: Path) -> dict[str, Any]:
    out = {
        "batch_dir": str(batch_dir),
        "n_total": 0,
        "n_intercepted": 0,
        "n_judge_match": 0,
        "n_judge_mismatch": 0,
        "n_judge_error": 0,
        "tasks": [],
    }
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
        match: Any = None
        judge_p = run_dir / "judge.json"
        if judge_p.exists():
            try:
                match = json.loads(judge_p.read_text()).get("match")
            except Exception:
                pass
        if intercepted:
            if match is True:
                out["n_judge_match"] += 1
            elif match is False:
                out["n_judge_mismatch"] += 1
            else:
                out["n_judge_error"] += 1
        out["tasks"].append({
            "test_case": meta.get("test_case"),
            "intercepted": intercepted,
            "judge_match": match,
            "final_pass": bool(intercepted and match is True),
        })
    out["pass_rate_stage1_only"] = (
        out["n_intercepted"] / out["n_total"] if out["n_total"] else 0
    )
    out["pass_rate_with_judge"] = (
        out["n_judge_match"] / out["n_total"] if out["n_total"] else 0
    )
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--sweep-root",
        type=Path,
        default=Path.home() / "work/ClawBench/claw-output/sweep",
    )
    p.add_argument(
        "--judge-model",
        default="deepseek-v4-pro",
        help="Model name (key in models/models.yaml) used to judge",
    )
    p.add_argument(
        "--models-yaml",
        type=Path,
        default=Path.home() / "work/ClawBench/models/models.yaml",
    )
    p.add_argument("--workers", type=int, default=4, help="Parallel judge calls")
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-judge tasks that already have judge.json",
    )
    p.add_argument(
        "--limit", type=int, default=0, help="Cap how many tasks to judge (0 = all)"
    )
    p.add_argument(
        "--only-batch",
        type=Path,
        default=None,
        help="Limit to a single batch-*/ dir",
    )
    args = p.parse_args()

    cfg_all = yaml.safe_load(args.models_yaml.read_text())
    if args.judge_model not in cfg_all:
        print(f"ERROR: judge model {args.judge_model!r} not in {args.models_yaml}", file=sys.stderr)
        return 2
    judge_cfg = dict(cfg_all[args.judge_model])
    if not judge_cfg.get("api_key"):
        print(f"ERROR: judge {args.judge_model!r} has no api_key", file=sys.stderr)
        return 2

    if args.only_batch:
        run_dirs = find_run_dirs(args.only_batch)
    else:
        run_dirs = find_run_dirs(args.sweep_root)

    pending = []
    for rd in run_dirs:
        try:
            m = json.loads((rd / "run-meta.json").read_text())
            if m.get("intercepted") and (args.force or not (rd / "judge.json").exists()):
                pending.append(rd)
        except Exception:
            continue

    if args.limit:
        pending = pending[: args.limit]

    print(f"discovered {len(run_dirs)} tasks, judging {len(pending)} intercepted ones with {args.judge_model}")

    judged = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(rescore_one, judge_cfg, args.judge_model, rd, args.force): rd for rd in pending}
        for fut in as_completed(futs):
            rd = futs[fut]
            try:
                v = fut.result()
                judged += 1
                m = v.get("match") if v else None
                tag = {True: "MATCH", False: "MISS ", None: "ERR  "}.get(m, "?    ")
                print(f"  [{judged}/{len(pending)}] {tag} {rd.name[:80]}")
            except Exception as e:
                print(f"  err on {rd}: {e}")

    if args.only_batch:
        batches = [args.only_batch]
    else:
        batches = sorted({
            next((p for p in run.parents if p.name.startswith("batch-")), None)
            for run in run_dirs
        } - {None})
    print(f"\nrolling up {len(batches)} batches:")
    for bd in batches:
        try:
            roll = aggregate_batch(bd)
        except Exception as e:
            print(f"  err rolling up {bd}: {e}")
            continue
        out_p = bd / "rescore-summary.json"
        out_p.write_text(json.dumps(roll, indent=2, ensure_ascii=False))
        s1 = roll["pass_rate_stage1_only"] * 100
        s12 = roll["pass_rate_with_judge"] * 100
        label = bd.relative_to(bd.parent.parent.parent) if bd.is_relative_to(bd.parent.parent.parent) else bd
        print(
            f"  {label}: stage1={roll['n_intercepted']}/{roll['n_total']} ({s1:.1f}%) "
            f"+ judge match={roll['n_judge_match']} miss={roll['n_judge_mismatch']} err={roll['n_judge_error']} "
            f"→ final={s12:.1f}%"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
