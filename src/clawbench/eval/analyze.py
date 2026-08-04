"""``clawbench-analyze`` — aggregate error analysis over a batch of run outputs (#159).

Reads a directory of completed run outputs (each ``<run>/data/interception.json``,
optionally ``<run>/reward.json``), reuses the per-run classifier, and produces an
aggregate report: Stage-1 (interception) and Stage-2 (judged) rates, a per-category
breakdown, a failure taxonomy, the interceptor false-positive check, and the
self-report-vs-actual gap. Output as Markdown and/or JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from clawbench.runner.run_support.results import classify_run

# heuristic: an agent message claiming the task is finished
_CLAIM_RE = re.compile(
    r"\b(task (is )?(complete|completed|done|finished|accomplished)|"
    r"successfully (completed|submitted|saved|booked)|i (have|'ve) (completed|finished|done))\b",
    re.IGNORECASE,
)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _task_category(run_dir: Path, task: dict[str, Any] | None) -> str:
    """Category from task metadata, else derived from the task-id name segments."""
    if isinstance(task, dict):
        meta = task.get("metadata")
        if isinstance(meta, dict) and meta.get("category"):
            return str(meta["category"])
    # e.g. "v2-536-daily-life-shopping-etsy" -> "daily-life-shopping"
    parts = run_dir.name.split("-")
    if len(parts) >= 4 and parts[0].startswith("v"):
        return "-".join(parts[2:-1]) or "uncategorized"
    return "uncategorized"


def _claimed_success(run_dir: Path) -> bool:
    msgs = run_dir / "data" / "agent-messages.jsonl"
    if not msgs.is_file():
        return False
    try:
        text = msgs.read_text()
    except OSError:
        return False
    return bool(_CLAIM_RE.search(text))


def discover_runs(runs_dir: Path) -> list[Path]:
    """Run dirs = any dir containing data/interception.json."""
    return sorted({p.parent.parent for p in runs_dir.glob("*/data/interception.json")})


def run_summary(run_dir: Path) -> dict[str, Any]:
    """Per-run: task id/category, Stage-1 intercept, Stage-2 judged, failure class."""
    interception = _read_json(run_dir / "data" / "interception.json")
    intercepted = bool(
        isinstance(interception, dict) and interception.get("intercepted")
    )
    task = _read_json(run_dir / "data" / "task.json") or _read_json(
        run_dir / "task.json"
    )

    reward = _read_json(run_dir / "reward.json")
    judged = None
    if isinstance(reward, dict) and reward.get("reward") is not None:
        judged = float(reward["reward"]) >= 1.0

    cls = classify_run(run_dir, intercepted, recording_required=False)
    return {
        "task": run_dir.name,
        "category": _task_category(run_dir, task if isinstance(task, dict) else None),
        "intercepted": intercepted,
        "judged": judged,
        "result_category": cls.get("result_category"),
        "actions": cls.get("metrics", {}).get("actions", 0),
        "claimed_success": _claimed_success(run_dir),
    }


def analyze_batch(runs_dir: Path) -> dict[str, Any]:
    """Aggregate the per-run summaries into an error-analysis report dict."""
    runs = [run_summary(r) for r in discover_runs(runs_dir)]
    n = len(runs)
    intercepted = sum(1 for r in runs if r["intercepted"])
    have_judge = [r for r in runs if r["judged"] is not None]
    judged_pass = sum(1 for r in have_judge if r["judged"])

    # per-category Stage-1 breakdown
    by_cat: dict[str, dict[str, int]] = {}
    for r in runs:
        c = by_cat.setdefault(r["category"], {"n": 0, "intercepted": 0})
        c["n"] += 1
        c["intercepted"] += int(r["intercepted"])

    # validity checks
    zero_action_intercepted = sum(
        1 for r in runs if r["actions"] == 0 and r["intercepted"]
    )

    # self-report gap: claimed success but did NOT pass (judged False, or not intercepted)
    def _failed(r: dict[str, Any]) -> bool:
        return (r["judged"] is False) or (r["judged"] is None and not r["intercepted"])

    claimed_but_failed = sum(1 for r in runs if r["claimed_success"] and _failed(r))
    claimed_total = sum(1 for r in runs if r["claimed_success"])

    return {
        "n_runs": n,
        "stage1_intercepted": intercepted,
        "stage1_rate": round(intercepted / n, 4) if n else 0.0,
        "stage2_judged_of": len(have_judge),
        "stage2_pass": judged_pass,
        "stage2_rate": round(judged_pass / len(have_judge), 4) if have_judge else None,
        "failure_taxonomy": dict(Counter(r["result_category"] for r in runs)),
        "by_category": {
            k: {**v, "rate": round(v["intercepted"] / v["n"], 4)}
            for k, v in sorted(by_cat.items())
        },
        "interceptor_false_positives": zero_action_intercepted,  # should be 0
        "self_report_claimed": claimed_total,
        "self_report_claimed_but_failed": claimed_but_failed,
    }


def format_report(stats: dict[str, Any]) -> str:
    n = stats["n_runs"]
    lines = ["# ClawBench batch error analysis", ""]
    lines.append(f"- **Runs:** {n}")
    lines.append(
        f"- **Stage-1 intercepted:** {stats['stage1_intercepted']}/{n} "
        f"({stats['stage1_rate']:.0%})"
    )
    if stats["stage2_rate"] is not None:
        lines.append(
            f"- **Stage-2 judged pass:** {stats['stage2_pass']}/{stats['stage2_judged_of']} "
            f"({stats['stage2_rate']:.0%})"
        )
    lines.append(
        f"- **Interceptor false-positives** (0-action but intercepted): "
        f"{stats['interceptor_false_positives']} (should be 0)"
    )
    if stats["self_report_claimed"]:
        lines.append(
            f"- **Self-report gap:** {stats['self_report_claimed_but_failed']}/"
            f"{stats['self_report_claimed']} runs that claimed success actually failed"
        )
    lines += ["", "## Failure taxonomy", ""]
    for k, v in sorted(stats["failure_taxonomy"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {k or 'unknown'}: {v}")
    lines += [
        "",
        "## Per-category Stage-1",
        "",
        "| category | n | intercepted | rate |",
        "|---|--:|--:|--:|",
    ]
    for cat, v in stats["by_category"].items():
        lines.append(f"| {cat} | {v['n']} | {v['intercepted']} | {v['rate']:.0%} |")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clawbench-analyze",
        description="Aggregate error analysis over a batch of ClawBench run outputs.",
    )
    p.add_argument(
        "--runs-dir",
        type=Path,
        required=True,
        help="Batch output dir (contains <run>/data/)",
    )
    p.add_argument(
        "--out", type=Path, default=None, help="Write the Markdown report here"
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print the stats as JSON instead of Markdown",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.runs_dir.is_dir():
        print(f"ERROR: runs dir not found: {args.runs_dir}", file=sys.stderr)
        return 1
    stats = analyze_batch(args.runs_dir)
    if stats["n_runs"] == 0:
        print(f"ERROR: no runs found under {args.runs_dir}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        report = format_report(stats)
        if args.out:
            args.out.write_text(report)
            print(f"Wrote report to {args.out}")
        else:
            print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
