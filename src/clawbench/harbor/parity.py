"""Parity check: native ClawBench runner vs Harbor-as-runner (``clawbench-harbor-parity``).

Runs the same ``{case × model}`` cell two ways and diffs the scoring outcome:

* **native** — ``python -m clawbench.runner.run <case> <model> --harness <h>``,
  reading ``run-meta.json``'s ``intercepted`` / ``judge_match`` / ``pass``.
* **harbor** — ``clawbench-export-harbor`` then ``harbor run ... --env docker``
  (with ``--ve JUDGE_API_KEY=...`` when judging, since the key is never baked into
  the shareable task.toml), reading the verifier's ``reward.json`` (1.0 == pass,
  json-first then ``reward.txt`` fallback) and ``verify-result.json``
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
import os
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


def _read_reward(trial_root: Path) -> float | None:
    """Read the Harbor reward, json-first (mirrors Harbor 0.13.1's precedence).

    Harbor reads ``reward.json`` (``{"reward": <float>}``) first and falls back to
    the bare-float ``reward.txt``; the parity reader does the same so it agrees
    with whatever Harbor recorded.
    """
    jsons = sorted(trial_root.rglob("reward.json"))
    if jsons:
        try:
            blob = json.loads(jsons[-1].read_text())
            val = blob.get("reward") if isinstance(blob, dict) else None
            if val is not None:
                return float(val)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    txts = sorted(trial_root.rglob("reward.txt"))
    if txts:
        try:
            return float(txts[-1].read_text().strip())
        except (OSError, ValueError):
            pass
    return None


def _read_harbor_result(trial_root: Path) -> dict[str, Any]:
    """Read the Harbor verifier reward + verify-result.json from a run tree."""
    result: dict[str, Any] = {"intercept": None, "judge": None, "pass": None}
    reward = _read_reward(trial_root)
    if reward is not None:
        result["pass"] = reward >= 1.0
        result["reward"] = reward
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
    *,
    judge_api_key: str | None = None,
) -> dict[str, Any]:
    """Run ``harbor run`` against an exported task dir and read the reward.

    ``judge_api_key`` is injected into the verifier at runtime via ``--ve
    JUDGE_API_KEY=...`` (the key is never baked into the shareable task.toml; see
    clawbench.harbor.export). Omit it for ``--no-judge`` exports.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    # NB: do not pass ``--agent clawbench`` -- ``--agent`` is typed as Harbor's
    # ``AgentName`` enum (oracle/terminus/hermes/...), so it fails validation.
    # ``--agent-import-path`` alone selects ClawbenchHarnessAgent (see agent.py).
    cmd = [
        "harbor",
        "run",
        "--path",
        str(harbor_task_dir),
        "--agent-import-path",
        "clawbench.harbor.agent:ClawbenchHarnessAgent",
        "--ak",
        f"harness={harness}",
        "--model",
        model,
        "--env",
        "docker",
        "--output-dir",
        str(output_dir),
    ]
    if judge_api_key:
        cmd += ["--ve", f"JUDGE_API_KEY={judge_api_key}"]
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
        "--judge",
        default="gemini-3.5-flash",
        help="Judge model key in models.yaml used to resolve the runtime "
        "JUDGE_API_KEY for the Harbor verifier (ignored with --no-judge).",
    )
    parser.add_argument(
        "--models-yaml",
        type=Path,
        default=None,
        help="Path to models.yaml for resolving the judge key (default: workspace).",
    )
    parser.add_argument(
        "--judge-api-key",
        default=None,
        help="Judge API key to inject via 'harbor run --ve JUDGE_API_KEY=...'. "
        "Defaults to $JUDGE_API_KEY, then the key resolved from models.yaml.",
    )
    parser.add_argument(
        "--skip-native", action="store_true", help="Only run the Harbor side."
    )
    parser.add_argument(
        "--skip-harbor", action="store_true", help="Only run the native side."
    )
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    case = args.case_dir.name

    # Resolve the judge key once (never baked into task.toml; injected at runtime).
    judge_api_key: str | None = None
    if not args.no_judge and not args.skip_harbor:
        judge_api_key = args.judge_api_key or os.environ.get("JUDGE_API_KEY")
        if not judge_api_key:
            from clawbench.harbor.export import _load_judge_env

            judge_api_key = _load_judge_env(args.judge, args.models_yaml).get(
                "JUDGE_API_KEY"
            )

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
            judge_api_key=judge_api_key,
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
