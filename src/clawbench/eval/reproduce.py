"""Reproduce a published ClawBench leaderboard row from public HF traces.

Workflow:
  1. Download a model's V2 trace subset from TIGER-Lab/ClawBenchV2Trace.
  2. Re-judge it using `deepseek-v4-pro` under the lenient + strict rubrics
     (default; configurable via --rubric).
  3. Compare your local Intercept%, Reward(lenient)%, Reward(strict)% against
     the published row.
  4. Print PASS if all metrics land within --tolerance pp of ours, else FAIL
     with the per-metric delta.

Example:
  clawbench-reproduce --model deepseek-v4-flash
  clawbench-reproduce --model claude-opus-4-7 --tolerance 1.5 --rubric lenient
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Published reference rows (from claw-bench.com / TIGER-Lab/ClawBenchV2Trace).
# Each entry: model -> (intercept_pct, reward_lenient_pct, reward_strict_pct, n).
PUBLISHED_V2_HERMES: dict[str, tuple[float, float, float, int]] = {
    "claude-opus-4-7": (54.6, 44.6, 24.6, 130),
    "gpt-5.5": (45.4, 35.4, 18.5, 130),
    "glm-5.1": (48.5, 34.6, 17.7, 130),
    "deepseek-v4-pro": (43.9, 33.9, 12.3, 130),
    "openrouter-owl-alpha": (14.6, 0.0, 0.0, 130),
    "z-ai/glm-4.5-air:free": (4.6, 2.3, 0.8, 130),
    "deepseek-v4-flash:free": (3.1, 2.3, 0.0, 129),
    "minimax-m2.5:free": (2.3, 1.5, 0.0, 130),
    # Aliases for common short names
    "deepseek-v4-flash": (3.1, 2.3, 0.0, 129),
    "glm-4.5-air": (4.6, 2.3, 0.8, 130),
}

REPO_ID = "TIGER-Lab/ClawBenchV2Trace"
REMOTE_PREFIX = "batch-aligned-20260520"


def slug(model: str) -> str:
    """Best-effort HF subdir name. Matches what we upload as <model_label>."""
    return model.replace("/", "_").replace(":", "-")


def download(model: str, dest: Path) -> Path:
    """Download model's trace subset from HF to dest. Return root path."""
    pattern = f"{REMOTE_PREFIX}/{slug(model)}/**"
    cmd = [
        "hf",
        "download",
        "--repo-type",
        "dataset",
        REPO_ID,
        "--include",
        pattern,
        "--local-dir",
        str(dest),
    ]
    print("  $", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit(f"hf download failed: {r.returncode}")
    return dest / REMOTE_PREFIX / slug(model)


def rescore(batch_dir: Path, judge_model: str, rubric: str) -> dict[str, Any]:
    """Invoke clawbench-rescore on the downloaded batch dir."""
    cmd = [
        sys.executable,
        "-m",
        "clawbench.eval.rescore",
        "--only-batch",
        str(batch_dir),
        "--judge-model",
        judge_model,
        "--rubric",
        rubric,
        "--no-eval-results",
    ]
    print("  $", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit(f"rescore failed: {r.returncode}")
    summary_p = batch_dir / "rescore-summary.json"
    return json.loads(summary_p.read_text())


def verdict(
    observed: tuple[float, float, float, int],
    published: tuple[float, float, float, int],
    tolerance: float,
) -> tuple[bool, str]:
    labels = ["Intercepted%", "Reward(lenient)%", "Reward(strict)%"]
    lines = [f"  {'metric':<20} {'observed':>10} {'published':>10} {'delta':>10}"]
    ok = True
    for lbl, obs, pub in zip(labels, observed[:3], published[:3]):
        d = obs - pub
        flag = "OK" if abs(d) <= tolerance else "FAIL"
        if flag == "FAIL":
            ok = False
        lines.append(f"  {lbl:<20} {obs:>9.1f}% {pub:>9.1f}% {d:>+8.1f}pp [{flag}]")
    return ok, "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--model",
        required=True,
        help="Model published row to reproduce. Available: "
        + ", ".join(sorted(PUBLISHED_V2_HERMES.keys())),
    )
    p.add_argument("--judge-model", default="deepseek-v4-pro")
    p.add_argument(
        "--rubric",
        choices=["lenient", "strict", "both"],
        default="both",
        help="Default 'both' computes both columns for full diff.",
    )
    p.add_argument(
        "--tolerance",
        type=float,
        default=2.0,
        help="Pass if each metric is within ±tolerance pp (default 2.0)",
    )
    p.add_argument(
        "--work-dir",
        type=Path,
        default=Path("./reproduce-cache"),
        help="Local dir for HF download (default ./reproduce-cache)",
    )
    p.add_argument(
        "--keep-cache",
        action="store_true",
        help="Keep downloaded traces after run (default: delete)",
    )
    args = p.parse_args()

    if args.model not in PUBLISHED_V2_HERMES:
        print(
            f"ERROR: unknown model {args.model!r}. Available:\n  "
            + "\n  ".join(sorted(PUBLISHED_V2_HERMES)),
            file=sys.stderr,
        )
        return 2

    published = PUBLISHED_V2_HERMES[args.model]
    args.work_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"== Reproducing {args.model} (n={published[3]}, tolerance ±{args.tolerance}pp) ==\n"
    )
    print("[1/3] Download trace subset from HF ...")
    batch_dir = download(args.model, args.work_dir)

    # Need a model batch root; HF subset puts task dirs under
    # batch-aligned-.../<model>/batch-.../<model>/ → walk down.
    candidates = [p for p in batch_dir.rglob("batch-*") if p.is_dir()]
    if not candidates:
        # No nested batch-* dir? The batch_dir itself is the root.
        candidates = [batch_dir]
    inner_batch = candidates[0]
    # If there's a model sub-dir inside, use it
    sub = [
        c
        for c in inner_batch.iterdir()
        if c.is_dir() and not c.name.startswith("batch-logs")
    ]
    if sub and any(
        (
            c / next(c.iterdir(), Path("/dev/null")) / "data" / "interception.json"
        ).exists()
        for c in sub
    ):
        inner_batch = sub[0]
    print(f"  → batch root: {inner_batch}")

    print(f"\n[2/3] Re-judge with {args.judge_model} (rubric={args.rubric}) ...")
    summary = rescore(inner_batch, args.judge_model, args.rubric)

    n = summary["n_total"]
    observed_icpt = 100.0 * summary["n_intercepted"] / n if n else 0.0
    observed_lenient = 100.0 * summary.get("reward_pct_lenient", 0)
    observed_strict = 100.0 * summary.get("reward_pct_strict", 0)
    observed = (observed_icpt, observed_lenient, observed_strict, n)

    print("\n[3/3] Compare to published row ...")
    ok, table = verdict(observed, published, args.tolerance)
    print(table)
    print()
    if ok:
        print(
            f"✓ PASS — reproduction within ±{args.tolerance} pp of published numbers."
        )
    else:
        print(f"✗ FAIL — at least one metric deviates more than ±{args.tolerance} pp.")
        print("  Possible causes:")
        print("  - Different judge model (we use deepseek-v4-pro on OpenRouter).")
        print(
            "  - Different rubric (our prompts in src/clawbench/runner/judge_llm.py)."
        )
        print("  - HF dataset rev drift — try `hf download --revision <commit>`.")

    if not args.keep_cache:
        shutil.rmtree(args.work_dir, ignore_errors=True)
        print(f"  (deleted {args.work_dir}; pass --keep-cache to keep traces)")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
