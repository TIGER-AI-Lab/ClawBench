"""Harbor verifier reward shim for ClawBench tasks.

Run by the Harbor task's ``tests/test.sh`` as ``python -m clawbench.harbor.verify``.
It reuses ClawBench's *pure-Python* scoring so the reward is identical to the
native runner:

* **Stage 1** — ``run_support.results.{ensure_interception,classify_run,print_results}``
  read ``/data/interception.json`` (produced by the in-container interceptor) and
  decide whether the agent's final request matched the eval schema.
* **Stage 2** — ``runner.judge.judge_request`` asks an LLM whether the intercepted
  request actually fulfils the instruction. Skipped ONLY when ``--no-judge`` (or
  ``CLAWBENCH_NO_JUDGE=1``) is set. If judging is required but no judge config /
  credentials are present, the verifier **fails closed** (reward 0.0 + diagnostic)
  rather than silently passing.

reward = 1.0 if intercepted AND (no_judge OR judge.match) else 0.0

The reward is written to BOTH ``/logs/verifier/reward.json`` (the canonical
``{"reward": <float>}`` that Harbor 0.13.1 reads first) and ``/logs/verifier/
reward.txt`` (the bare-float fallback Harbor reads when reward.json is absent).
``--reward-file`` / ``HARBOR_REWARD_FILE`` overrides the txt path (reward.json is
written alongside it). A diagnostic ``verify-result.json`` is written next to the
reward files.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from clawbench.runner.run_support.results import (
    classify_run,
    ensure_interception,
    print_results,
)

# Harbor's Linux convention; see harbor.models.trial.paths.EnvironmentPaths.
# Harbor 0.13.1 reads reward.json first, falling back to reward.txt; we write both.
DEFAULT_REWARD_FILE = Path("/logs/verifier/reward.txt")
# ClawBench output root inside the container: /data is the run dir's data/ dir,
# so the "output_dir" the results helpers expect is its parent.
DEFAULT_DATA_DIR = Path("/data")


def _bool_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _load_judge_cfg() -> dict[str, Any] | None:
    """Build the judge model_cfg from env, or return None to skip Stage 2.

    Set by the exported ``tests/test.sh``:
        JUDGE_MODEL, JUDGE_BASE_URL, JUDGE_API_TYPE, JUDGE_API_KEY
    """
    model = os.environ.get("JUDGE_MODEL", "").strip()
    base_url = os.environ.get("JUDGE_BASE_URL", "").strip()
    api_type = os.environ.get("JUDGE_API_TYPE", "").strip()
    api_key = os.environ.get("JUDGE_API_KEY", "").strip()
    if not (model and base_url and api_type and api_key):
        return None
    return {
        "model": model,
        "base_url": base_url,
        "api_type": api_type,
        "api_key": api_key,
    }


def _read_instruction(data_dir: Path) -> str:
    """Recover the task instruction for the judge (env first, then schema file)."""
    instruction = os.environ.get("INSTRUCTION", "").strip()
    if instruction:
        return instruction
    # The interception blob carries no instruction; fall back to the bundled
    # eval-schema.json's sibling instruction.txt if the image baked one.
    for candidate in (
        data_dir.parent / "instruction.txt",
        Path("/clawbench/instruction.txt"),
    ):
        if candidate.exists():
            return candidate.read_text().strip()
    return ""


def _read_judge_context() -> dict[str, Any] | None:
    raw = os.environ.get("JUDGE_CONTEXT", "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def compute_reward(
    data_dir: Path,
    *,
    no_judge: bool,
    judge_cfg: dict[str, Any] | None,
    instruction: str,
    judge_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Stage 1 (+ optional Stage 2) and return a result dict with ``reward``.

    ``data_dir`` is the ``/data`` directory; the results helpers operate on its
    parent (the "output dir"). Pure-Python, no Docker — identical to native.
    """
    output_dir = data_dir.parent

    # Stage 1: make sure interception.json exists, then classify + read it.
    ensure_interception(output_dir)
    intercepted = bool(print_results(output_dir))
    classification = classify_run(output_dir, intercepted)

    result: dict[str, Any] = {
        "intercepted": intercepted,
        "stage1": True,
        "failure_category": classification.get("failure_category"),
        "judge": None,
        "judge_match": None,
        "no_judge": no_judge,
        "error": None,
    }

    # Fail closed: judging is required (``--no-judge`` not set) but no judge config
    # / credentials reached the verifier -- e.g. ``harbor run --ve JUDGE_API_KEY=``
    # was omitted, or JUDGE_MODEL/BASE_URL/API_TYPE/API_KEY are not all set. A
    # missing judge must NEVER be treated as an automatic pass.
    if not no_judge and judge_cfg is None:
        result["error"] = (
            "judge required but not configured: set JUDGE_MODEL / JUDGE_BASE_URL / "
            "JUDGE_API_TYPE / JUDGE_API_KEY (inject the key at runtime via "
            "`harbor run --ve JUDGE_API_KEY=...`), or pass --no-judge to score "
            "Stage 1 only."
        )
        result["pass"] = False
        result["reward"] = 0.0
        return result

    judge_match: bool | None = None
    if intercepted and not no_judge and judge_cfg is not None:
        from clawbench.runner.judge import judge_request

        interception_path = data_dir / "interception.json"
        intercept_blob: dict[str, Any] = {}
        if interception_path.exists():
            try:
                loaded = json.loads(interception_path.read_text())
                if isinstance(loaded, dict):
                    intercept_blob = loaded
            except json.JSONDecodeError:
                intercept_blob = {}
        judge_result = judge_request(
            judge_cfg,
            judge_cfg.get("model", "judge"),
            instruction,
            intercept_blob,
            judge_context=judge_context,
        )
        result["judge"] = judge_result
        judge_match = judge_result.get("match")
        result["judge_match"] = judge_match

    # judge_cfg is guaranteed non-None here when judging is required (the missing
    # case fails closed above), so a required judge must return match=True to pass.
    passed = bool(intercepted and (no_judge or judge_match is True))
    result["pass"] = passed
    result["reward"] = 1.0 if passed else 0.0
    return result


def _write_reward(reward_file: Path, result: dict[str, Any]) -> None:
    """Persist the reward + diagnostic for Harbor.

    Writes the canonical ``reward.json`` (``{"reward": <float>}``, read first by
    Harbor 0.13.1) AND the bare-float ``reward.txt`` fallback, plus a richer
    ``verify-result.json`` diagnostic. ``reward.json`` sits next to ``reward_file``.
    """
    reward_file.parent.mkdir(parents=True, exist_ok=True)
    reward = float(result["reward"])
    (reward_file.with_name("reward.json")).write_text(
        json.dumps({"reward": reward})
    )
    reward_file.write_text(f"{reward}")
    (reward_file.parent / "verify-result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ClawBench reward shim for the Harbor verifier."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("CLAWBENCH_DATA_DIR") or DEFAULT_DATA_DIR),
        help="Directory holding interception.json (default: /data).",
    )
    parser.add_argument(
        "--reward-file",
        type=Path,
        default=Path(os.environ.get("HARBOR_REWARD_FILE") or DEFAULT_REWARD_FILE),
        help="Path to write the reward float (default: /logs/verifier/reward.txt).",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        default=_bool_env("CLAWBENCH_NO_JUDGE"),
        help="Skip the LLM judge; reward = intercepted (Stage 1 only).",
    )
    args = parser.parse_args(argv)

    data_dir: Path = args.data_dir
    reward_file: Path = args.reward_file

    judge_cfg = None if args.no_judge else _load_judge_cfg()
    instruction = _read_instruction(data_dir)
    judge_context = _read_judge_context()

    result = compute_reward(
        data_dir,
        no_judge=args.no_judge,
        judge_cfg=judge_cfg,
        instruction=instruction,
        judge_context=judge_context,
    )

    _write_reward(reward_file, result)

    print(
        f"ClawBench reward: {result['reward']} "
        f"(intercepted={result['intercepted']}, "
        f"judge_match={result['judge_match']}, no_judge={result['no_judge']})"
    )
    if result.get("error"):
        print(f"ClawBench verify error: {result['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
