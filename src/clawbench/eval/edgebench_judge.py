"""``clawbench-edgebench-judge`` — score ClawBench evidence as EdgeBench structured_json.

EdgeBench (SForge) judges an agent's *submitted archive* offline in an ephemeral
Judge container: its ``eval_cmd`` reads the evidence, prints a
``structured_json`` block, and SForge parses the ``score``/``valid`` from it.

ClawBench's two-stage reward maps onto this cleanly: the Work-side interceptor
captures the target request into ``evidence/interception.json``; this module
(the Judge ``eval_cmd``) re-scores that captured evidence — Stage-1 (was the
target intercepted) ∧ Stage-2 (LLM judge confirms intent) — and emits the
structured_json block SForge expects.

Judge config comes from ``CLAWBENCH_JUDGE_*`` env (injected into the Judge
container via ``SFORGE_JUDGE_EXTRA_ENV``); ``--no-judge`` scores Stage-1 only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from clawbench.runner.judge import judge_request

# SForge structured_json markers (grading._grade_structured looks for these).
START_MARKER = ">>>>> Start Structured Result"
END_MARKER = ">>>>> End Structured Result"


def _judge_cfg_from_env() -> dict[str, str] | None:
    """Build the judge model config from CLAWBENCH_JUDGE_* env, or None if unset."""
    base_url = os.environ.get("CLAWBENCH_JUDGE_BASE_URL", "").strip()
    api_key = os.environ.get("CLAWBENCH_JUDGE_API_KEY", "").strip()
    if not base_url or not api_key:
        return None
    return {
        "base_url": base_url,
        "api_key": api_key,
        "api_type": os.environ.get("CLAWBENCH_JUDGE_API_TYPE", "openai-completions"),
    }


_MISSING = object()


def _load_interception(evidence_dir: Path) -> Any:
    """Return the parsed interception (any JSON type), None if absent, or _MISSING if unreadable."""
    path = evidence_dir / "interception.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return _MISSING


def score_evidence(
    task: dict[str, Any],
    evidence_dir: Path,
    *,
    judge_cfg: dict[str, str] | None,
    judge_model: str,
    no_judge: bool = False,
) -> dict[str, Any]:
    """Score captured evidence; return an EdgeBench structured_json result dict."""
    instruction = str(task.get("instruction") or "")
    judge_context = task.get("judge_context")
    intercept = _load_interception(evidence_dir)
    is_intercept = isinstance(intercept, dict) and intercept.get("intercepted") is True

    def result(
        score: float, valid: bool, summary: str, stage1: str, stage2: str
    ) -> dict[str, Any]:
        return {
            "valid": valid,
            "score": float(score),
            "pass_rate": float(score),
            "summary": summary[:4096],
            "details": [
                {"name": "stage1-interception", "status": stage1},
                {"name": "stage2-judge", "status": stage2},
            ],
            "metrics": {"intercepted": is_intercept},
        }

    # Stage 1 — validate the captured evidence, then check the target was intercepted.
    if intercept is _MISSING:
        return result(
            0.0, False, "malformed evidence/interception.json", "ERROR", "SKIPPED"
        )
    if intercept is None:
        return result(
            0.0, True, "no evidence/interception.json found", "FAILED", "SKIPPED"
        )
    if not isinstance(intercept, dict):
        return result(
            0.0, False, "interception.json is not an object", "ERROR", "SKIPPED"
        )
    # require an explicit boolean True (a truthy string like "false" must NOT pass)
    if intercept.get("intercepted") is not True:
        return result(0.0, True, "target request not intercepted", "FAILED", "SKIPPED")
    if not isinstance(intercept.get("request"), dict):
        return result(
            0.0, False, "intercepted but no request object", "ERROR", "SKIPPED"
        )

    if no_judge:
        return result(
            1.0,
            True,
            "intercepted (Stage-1 only, judging disabled)",
            "PASSED",
            "SKIPPED",
        )

    # Stage 2 — LLM judge confirms the intercepted request fulfils the instruction.
    if judge_cfg is None:
        # Judging required but unconfigured: fail closed (never silently pass).
        return result(
            0.0,
            False,
            "judge required but CLAWBENCH_JUDGE_* unconfigured",
            "PASSED",
            "ERROR",
        )
    try:
        verdict = judge_request(
            judge_cfg, judge_model, instruction, intercept, judge_context=judge_context
        )
    except Exception:
        # Never let a judge/transport exception suppress the structured_json block;
        # fail closed with a category (not the raw error, which may carry secrets).
        return result(0.0, False, "judge call raised an exception", "PASSED", "ERROR")
    match = verdict.get("match")
    if verdict.get("error"):
        # judge_request returns a short error category; don't echo raw provider text.
        return result(0.0, False, "judge call failed", "PASSED", "ERROR")
    # Use generic summaries — the judge's free-text reason quotes the intercepted
    # request body, which can contain credentials/PII; never echo it to SForge output.
    if match is True:
        return result(
            1.0, True, "intercepted request fulfils the task", "PASSED", "PASSED"
        )
    return result(
        0.0, True, "intercepted request does not fulfil the task", "PASSED", "FAILED"
    )


def emit_structured_json(result: dict[str, Any]) -> str:
    """Wrap a result dict in the SForge structured_json markers."""
    return f"{START_MARKER}\n{json.dumps(result, ensure_ascii=False)}\n{END_MARKER}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clawbench-edgebench-judge",
        description="Score ClawBench evidence and print an EdgeBench structured_json block.",
    )
    p.add_argument(
        "--task-json",
        type=Path,
        required=True,
        help="Task JSON (instruction + judge_context)",
    )
    p.add_argument(
        "--evidence-dir",
        type=Path,
        required=True,
        help="Submitted evidence dir (has interception.json)",
    )
    p.add_argument(
        "--judge-model",
        default=None,
        help="Judge model name (else CLAWBENCH_JUDGE_MODEL env)",
    )
    p.add_argument(
        "--no-judge", action="store_true", help="Score Stage-1 (interception) only"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        task = json.loads(args.task_json.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read task json: {e}", file=sys.stderr)
        return 1
    judge_model = args.judge_model or os.environ.get(
        "CLAWBENCH_JUDGE_MODEL", "deepseek-v4-pro"
    )
    result = score_evidence(
        task,
        args.evidence_dir,
        judge_cfg=_judge_cfg_from_env(),
        judge_model=judge_model,
        no_judge=args.no_judge,
    )
    print(emit_structured_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
