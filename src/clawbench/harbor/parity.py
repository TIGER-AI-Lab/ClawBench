"""Parity check: native ClawBench runner vs Harbor-as-runner (``clawbench-harbor-parity``).

Runs the same ``{case × model}`` cell two ways and diffs the scoring outcome:

* **native** — ``python -m clawbench.runner.run <case> <model> --harness <h>``,
  reading ``run-meta.json``'s ``intercepted`` / ``judge_match`` / ``pass``.
* **harbor** — ``clawbench-export-harbor`` then ``harbor run ... --env docker``,
  reading the verifier's ``reward.txt`` (1.0 == pass) and ``verify-result.json``
  (``intercepted`` / ``judge_match``).

Because both paths share the exact same Stage-1 (``results.py``) and Stage-2
(``judge.py``) code, the outcome should match for a deterministic run; any gap is
attributable to agent non-determinism, not the scoring shim. Writes a
``parity.csv`` with columns: case,model,harness,native_intercept,harbor_intercept,
native_judge,harbor_judge,native_pass,harbor_pass,agree.

This module shells out to the two entrypoints (one container at a time) so it can
run on hosts where Harbor and the native runner coexist. It does not itself spawn
parallel work.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _find_run_meta(output_dir: Path) -> dict[str, Any] | None:
    metas = sorted(output_dir.rglob("run-meta.json"))
    if not metas:
        return None
    try:
        return json.loads(metas[-1].read_text())
    except (OSError, json.JSONDecodeError):
        return None


def run_native(
    case_dir: Path, model: str, harness: str, output_dir: Path, no_judge: bool
) -> dict[str, Any]:
    """Run the native ClawBench runner and read its run-meta.json verdict."""
    cmd = [
        sys.executable,
        "-m",
        "clawbench.runner.run",
        str(case_dir),
        model,
        "--harness",
        harness,
        "--output-dir",
        str(output_dir),
        "--no-upload",
    ]
    if no_judge:
        cmd.append("--no-judge")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    meta = _find_run_meta(output_dir) or {}
    return {
        "returncode": proc.returncode,
        "intercept": bool(meta.get("intercepted")),
        "judge": meta.get("judge_match"),
        "pass": bool(meta.get("pass")),
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def _read_harbor_result(trial_root: Path) -> dict[str, Any]:
    """Read the Harbor verifier reward + verify-result.json from a run tree."""
    result: dict[str, Any] = {"intercept": None, "judge": None, "pass": None}
    rewards = sorted(trial_root.rglob("reward.txt"))
    if rewards:
        try:
            reward = float(rewards[-1].read_text().strip())
            result["pass"] = reward >= 1.0
            result["reward"] = reward
        except (OSError, ValueError):
            pass
    verifies = sorted(trial_root.rglob("verify-result.json"))
    if verifies:
        try:
            blob = json.loads(verifies[-1].read_text())
            result["intercept"] = bool(blob.get("intercepted"))
            result["judge"] = blob.get("judge_match")
        except (OSError, json.JSONDecodeError):
            pass
    return result


def run_harbor(
    harbor_task_dir: Path,
    model: str,
    harness: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Run ``harbor run`` against an exported task dir and read the reward."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "harbor",
        "run",
        "--dataset",
        str(harbor_task_dir),
        "--agent-import-path",
        "clawbench.harbor.agent:ClawbenchHarnessAgent",
        "--agent",
        "clawbench",
        "--ak",
        f"harness={harness}",
        "--model",
        model,
        "--env",
        "docker",
        "--output-dir",
        str(output_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    result = _read_harbor_result(output_dir)
    result["returncode"] = proc.returncode
    result["stdout_tail"] = proc.stdout[-2000:]
    result["stderr_tail"] = proc.stderr[-2000:]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parity check: native ClawBench runner vs Harbor-as-runner."
    )
    parser.add_argument(
        "case_dir", type=Path, help="ClawBench case dir (test-cases/v2/<case>)."
    )
    parser.add_argument(
        "native_model",
        help="Model key in models.yaml for the native runner (e.g. gemini-3.5-flash).",
    )
    parser.add_argument(
        "harbor_model",
        help="LiteLLM model for harbor run (e.g. gemini/gemini-3.5-flash).",
    )
    parser.add_argument("--harness", default="harbor")
    parser.add_argument(
        "--harbor-task-dir",
        type=Path,
        required=True,
        help="An already-exported Harbor task dir for this case "
        "(clawbench-export-harbor output).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("parity-output"),
        help="Root for run outputs and parity.csv.",
    )
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument(
        "--skip-native", action="store_true", help="Only run the Harbor side."
    )
    parser.add_argument(
        "--skip-harbor", action="store_true", help="Only run the native side."
    )
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    case = args.case_dir.name

    native: dict[str, Any] = {}
    harbor: dict[str, Any] = {}
    if not args.skip_native:
        print(f"[native] {case} x {args.native_model} (harness={args.harness})")
        native = run_native(
            args.case_dir,
            args.native_model,
            args.harness,
            args.out_dir / "native",
            args.no_judge,
        )
        print(f"  native: {native.get('intercept')=} {native.get('pass')=}")
    if not args.skip_harbor:
        print(f"[harbor] {case} x {args.harbor_model} (harness={args.harness})")
        harbor = run_harbor(
            args.harbor_task_dir,
            args.harbor_model,
            args.harness,
            args.out_dir / "harbor",
        )
        print(f"  harbor: {harbor.get('intercept')=} {harbor.get('pass')=}")

    agree = native.get("pass") == harbor.get("pass") if native and harbor else ""
    row = {
        "case": case,
        "model": args.harbor_model,
        "harness": args.harness,
        "native_intercept": native.get("intercept"),
        "harbor_intercept": harbor.get("intercept"),
        "native_judge": native.get("judge"),
        "harbor_judge": harbor.get("judge"),
        "native_pass": native.get("pass"),
        "harbor_pass": harbor.get("pass"),
        "agree": agree,
    }

    csv_path = args.out_dir / "parity.csv"
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    print(f"\nparity row -> {csv_path}: {row}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
