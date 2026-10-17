"""Reproduce a published ClawBench leaderboard row from public HF traces.

Workflow:
  1. Download a model's V2 trace subset from TIGER-Lab/ClawBenchV2Trace.
  2. Re-judge it using `deepseek-v4-pro` under the lenient + strict rubrics
     (default; configurable via --rubric).
  3. Compare your local Intercept% and the requested Reward(lenient)% /
     Reward(strict)% columns against the published row.
  4. Print PASS (exit 0) if every compared metric lands within --tolerance pp
     of ours, FAIL (exit 1) with the per-metric delta if one does not, or
     INVALID (exit 3) if the evidence is incomplete: a different task count,
     a requested metric that was never computed, or judge-inconclusive results.

Example:
  clawbench-reproduce --model deepseek-v4-flash
  clawbench-reproduce --model claude-opus-4-7 --tolerance 1.5 --rubric lenient
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
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

# Reward columns each --rubric choice asks for; the others are not evaluated.
RUBRIC_COLUMNS: dict[str, tuple[str, ...]] = {
    "lenient": ("lenient",),
    "strict": ("strict",),
    "both": ("lenient", "strict"),
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


def observed_metrics(
    summary: dict[str, Any],
) -> tuple[float, float | None, float | None, int]:
    """Observed row from a rescore summary. None marks a rubric that did not run."""
    n = summary["n_total"]

    def pct(key: str) -> float | None:
        return 100.0 * summary[key] if key in summary else None

    intercepted = 100.0 * summary["n_intercepted"] / n if n else 0.0
    return (intercepted, pct("reward_pct_lenient"), pct("reward_pct_strict"), n)


def inconclusive_count(summary: dict[str, Any], rubric: str) -> int:
    """Judge results without a verdict, counted for the requested rubrics only."""
    return sum(summary.get(f"n_judge_err_{r}", 0) for r in RUBRIC_COLUMNS[rubric])


def verdict(
    observed: tuple[float, float | None, float | None, int],
    published: tuple[float, float, float, int],
    tolerance: float,
    rubric: str = "both",
    inconclusive: int = 0,
) -> tuple[str, str]:
    """Return "pass", "fail" or "invalid" (incomplete evidence) and the table."""
    requested = RUBRIC_COLUMNS[rubric]
    labels = ["Intercepted%", "Reward(lenient)%", "Reward(strict)%"]
    wanted = [True, "lenient" in requested, "strict" in requested]
    lines = [f"  {'metric':<20} {'observed':>10} {'published':>10} {'delta':>10}"]
    outcome = "pass"
    n_observed, n_published = observed[3], published[3]
    if n_observed == 0 or n_observed != n_published:
        outcome = "invalid"
        lines.append(
            f"  {'tasks':<20} {n_observed:>10} {n_published:>10} "
            f"{n_observed - n_published:>+10} [INVALID]"
        )
    if inconclusive:
        outcome = "invalid"
        lines.append(
            f"  {'judge inconclusive':<20} {inconclusive:>10} {'':>21} [INVALID]"
        )
    for lbl, want, obs, pub in zip(labels, wanted, observed[:3], published[:3]):
        if not want:
            lines.append(f"  {lbl:<20} {'not evaluated':>25}")
            continue
        if obs is None:
            outcome = "invalid"
            lines.append(f"  {lbl:<20} {'missing':>10} {pub:>9.1f}% {'':>10} [INVALID]")
            continue
        d = obs - pub
        flag = "OK" if abs(d) <= tolerance else "FAIL"
        # A mismatch measured on incomplete evidence stays invalid.
        if flag == "FAIL" and outcome == "pass":
            outcome = "fail"
        lines.append(f"  {lbl:<20} {obs:>9.1f}% {pub:>9.1f}% {d:>+8.1f}pp [{flag}]")
    return outcome, "\n".join(lines)


@contextmanager
def download_cache(work_dir: Path, keep_cache: bool) -> Iterator[Path]:
    """Own only a unique child directory, never the caller's work directory."""
    work_dir.mkdir(parents=True, exist_ok=True)
    if keep_cache:
        cache_dir = Path(tempfile.mkdtemp(prefix="clawbench-", dir=work_dir))
        print(f"  Cache retained at: {cache_dir}")
        yield cache_dir
    else:
        with tempfile.TemporaryDirectory(prefix="clawbench-", dir=work_dir) as tmp:
            cache_dir = Path(tmp)
            print(f"  Temporary cache: {cache_dir}")
            yield cache_dir


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
        help="Parent directory for an isolated download cache (default ./reproduce-cache)",
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
    with download_cache(args.work_dir, args.keep_cache) as cache_dir:
        print(
            f"== Reproducing {args.model} (n={published[3]}, tolerance ±{args.tolerance}pp) ==\n"
        )
        print("[1/3] Download trace subset from HF ...")
        batch_dir = download(args.model, cache_dir)

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

        print("\n[3/3] Compare to published row ...")
        outcome, table = verdict(
            observed_metrics(summary),
            published,
            args.tolerance,
            rubric=args.rubric,
            inconclusive=inconclusive_count(summary, args.rubric),
        )
        print(table)
        print()
        if outcome == "pass":
            print(
                f"✓ PASS — reproduction within ±{args.tolerance} pp of published numbers."
            )
        elif outcome == "invalid":
            print(
                "! INVALID — the evidence cannot confirm or refute the published row."
            )
            print("  Possible causes:")
            print("  - Partial download: the task count differs from the published n.")
            print("  - A requested rubric was never judged (check --rubric).")
            print("  - The judge returned no verdict for some runs; rescore and retry.")
        else:
            print(
                f"✗ FAIL — at least one metric deviates more than ±{args.tolerance} pp."
            )
            print("  Possible causes:")
            print("  - Different judge model (we use deepseek-v4-pro on OpenRouter).")
            print(
                "  - Different rubric (our prompts in src/clawbench/runner/judge_llm.py)."
            )
            print("  - HF dataset rev drift — try `hf download --revision <commit>`.")

        # 3 is also run.py's exit code for "judge never rendered a verdict".
        return {"pass": 0, "fail": 1, "invalid": 3}[outcome]


if __name__ == "__main__":
    sys.exit(main())
