"""``clawbench-edgebench-judge`` — score ClawBench evidence as EdgeBench structured_json.

EdgeBench (SForge) judges an agent's *submitted archive* offline in an ephemeral
Judge container: its ``eval_cmd`` reads the evidence, prints a
``structured_json`` block, and SForge parses the ``score``/``valid`` from it.

ClawBench's two-stage reward maps onto this cleanly: the Work-side interceptor
captures the target request into ``evidence/interception.json``; this module
(the Judge ``eval_cmd``) re-scores that captured evidence — Stage-1 ∧ Stage-2 —
and emits the structured_json block SForge expects. Because the agent controls
the submitted evidence, Stage-1 is **recomputed** against ``task["eval_schema"]``
(url_pattern + method + const body/params) rather than trusting the agent's
``intercepted`` flag; Stage-2 is the LLM judge over the verified request.

Judge config comes from ``CLAWBENCH_JUDGE_*`` env (injected into the Judge
container via ``SFORGE_JUDGE_EXTRA_ENV``); ``--no-judge`` scores Stage-1 only.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from typing import Any

from clawbench.runner.judge import judge_request
from clawbench.utils.paths import RUNTIME_ROOT


def _load_runtime_matching():
    """Load the Stage-1 predicate from the runtime-server directory.

    It lives beside the interceptor that runs it, because runtime-server/ is
    what gets COPYed into every task image. That directory name is not a valid
    module path, so it is loaded by file. Sharing the one copy is the point: a
    re-implementation here is what drifted from the live interceptor and made
    offline verdicts disagree with real runs.
    """
    import importlib.util

    path = RUNTIME_ROOT / "runtime-server" / "matching.py"
    spec = importlib.util.spec_from_file_location(
        "clawbench_runtime_matching", str(path)
    )
    if spec is None or spec.loader is None:  # pragma: no cover - packaging error
        raise ImportError(f"cannot load the Stage-1 matcher from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_matching = _load_runtime_matching()


def _verify_signature(intercept: dict[str, Any], secret: str) -> bool:
    """Verify a runtime-produced HMAC over the intercepted request.

    EdgeBench submits an agent-controlled archive, so Stage-1 evidence is only
    tamper-proof if the *trusted* runtime/entrypoint signs it with a secret the
    agent never sees (shared with the judge via ``SFORGE_JUDGE_EXTRA_ENV``). When
    ``CLAWBENCH_EVIDENCE_SECRET`` is set, the judge requires a valid
    ``signature = HMAC-SHA256(secret, canonical-json(request))`` and rejects
    forged/unsigned evidence.
    """
    sig = intercept.get("signature")
    if not isinstance(sig, str):
        return False
    payload = json.dumps(
        intercept.get("request"), sort_keys=True, separators=(",", ":")
    ).encode()
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def _stage1_match(request: dict[str, Any], eval_schema: Any) -> bool:
    """Recompute Stage-1 against the task schema — do NOT trust the agent's flag.

    The agent controls the submitted evidence archive, so re-verify that the
    submitted request actually hits the task's target, using the very predicate
    the in-container interceptor ran. This was a hand-maintained mirror of
    runtime-server until the two drifted; see ``_matching`` above.
    """
    return _matching.stage1_match(request, eval_schema)


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
    eval_schema = task.get("eval_schema")
    intercept = _load_interception(evidence_dir)
    matched = False  # set once we recompute Stage-1 against the schema

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
            "metrics": {"intercepted": matched},
        }

    # Stage 1 — validate the captured evidence, then RE-VERIFY the target was hit
    # against task["eval_schema"]. The agent controls the submitted archive, so its
    # "intercepted" flag is NOT trusted — the request must actually match the target.
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
    request = intercept.get("request")
    if not isinstance(request, dict):
        return result(
            0.0, True, "no intercepted request in evidence", "FAILED", "SKIPPED"
        )
    # Tamper-resistance: if a shared runtime/judge secret is configured, only
    # accept evidence the trusted runtime signed (the agent cannot forge it).
    secret = os.environ.get("CLAWBENCH_EVIDENCE_SECRET", "").strip()
    if secret and not _verify_signature(intercept, secret):
        return result(
            0.0, False, "evidence signature missing or invalid", "ERROR", "SKIPPED"
        )
    if not isinstance(eval_schema, dict) or not eval_schema.get("url_pattern"):
        # cannot independently verify the target → fail closed
        return result(
            0.0, False, "task eval_schema missing url_pattern", "ERROR", "SKIPPED"
        )
    matched = _stage1_match(request, eval_schema)
    if not matched:
        return result(
            0.0,
            True,
            "submitted request does not match the task target",
            "FAILED",
            "SKIPPED",
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
