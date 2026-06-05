"""Export ClawBench v2 tasks to Harbor task directories (``clawbench-export-harbor``).

A Harbor task directory has the canonical shape::

    <case>/
      task.toml          # version + [metadata] + [verifier]/[agent] timeouts
      instruction.md     # the task prompt (reuses run_support.task.build_instruction)
      environment/
        Dockerfile       # FROM the services-mode image, bakes eval-schema + persona
        eval-schema.json # the interceptor's match schema
        my-info/...      # the fixed persona bundle
      tests/
        test.sh          # the verifier: python -m clawbench.harbor.verify

Harbor runs it with::

    harbor run --dataset <out>/<case> \\
      --agent-import-path clawbench.harbor.agent:ClawbenchHarnessAgent \\
      --agent clawbench --ak harness=harbor \\
      --model gemini/gemini-3.5-flash --env docker

Honest gap: per-run disposable email + personalized /my-info has no Harbor
static-image hook, so we bake a fixed persona and *skip* tasks that require
account creation / email verification (logged to SKIPPED.md). Use ``--no-judge``
to export Stage-1-only tasks.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from clawbench.harbor.model_map import judge_api_type
from clawbench.runner.run_support.task import build_instruction, validate_task_data
from clawbench.utils.paths import SHARED_ROOT

DEFAULT_BASE_IMAGE = "clawbench-harbor-task"
DEFAULT_JUDGE_MODEL = "gemini-3.5-flash"

# Heuristic signals that a task needs a fresh, verifiable email inbox or account
# creation — which the Harbor static-image flow cannot provision per run.
_EMAIL_SIGNUP_CLASSES = {"registration", "signup", "sign-up"}
_EMAIL_SIGNUP_PATTERNS = (
    "verify your email",
    "verification email",
    "confirmation email",
    "verification code",
    "confirm your email",
    "check your inbox",
    "email confirmation",
    "create an account",
    "sign up for",
    "register for an account",
    "register an account",
)


def _sanitize_name(case: str) -> str:
    """Sanitize a case name into a Harbor ``org/name`` short-name component."""
    name = re.sub(r"[^a-z0-9._-]", "-", case.lower())
    name = re.sub(r"-+", "-", name).strip("-.")
    return name or "task"


def needs_email_or_signup(task: dict[str, Any]) -> tuple[bool, str]:
    """Return (should_skip, reason) for tasks requiring email/account creation."""
    metadata = task.get("metadata") or {}
    cls = str(metadata.get("class", "")).lower()
    if cls in _EMAIL_SIGNUP_CLASSES:
        return True, f"class={cls!r} requires account creation / email verification"
    instruction = str(task.get("instruction", "")).lower()
    for pat in _EMAIL_SIGNUP_PATTERNS:
        if pat in instruction:
            return True, f"instruction mentions {pat!r} (needs a fresh email inbox)"
    return False, ""


def _load_judge_env(
    judge_model: str | None, models_yaml: Path | None
) -> dict[str, str]:
    """Resolve the judge model config from models.yaml into baked env vars.

    Returns an empty dict when judging is disabled or the model is unavailable
    (the verifier then runs Stage-1 only). Raises on a configured-but-broken
    judge so export fails loudly rather than silently dropping Stage 2.
    """
    if not judge_model:
        return {}

    import yaml

    if models_yaml is None:
        from clawbench.runner.run_support.config import MODELS_YAML

        models_yaml = MODELS_YAML
    if not models_yaml.exists():
        raise SystemExit(
            f"ERROR: judge model {judge_model!r} requested but {models_yaml} not "
            "found. Pass --no-judge or provide models.yaml."
        )
    all_models = yaml.safe_load(models_yaml.read_text()) or {}
    if judge_model not in all_models:
        raise SystemExit(
            f"ERROR: judge model {judge_model!r} not in {models_yaml}. "
            f"Available: {', '.join(sorted(all_models))}"
        )
    cfg = dict(all_models[judge_model])
    base_url = str(cfg.get("base_url", "")).rstrip("/")
    api_type = str(cfg.get("api_type", ""))
    api_key = cfg.get("api_key") or (cfg.get("api_keys") or [None])[0]
    if not (base_url and api_type and api_key):
        raise SystemExit(
            f"ERROR: judge model {judge_model!r} missing base_url/api_type/api_key"
        )
    resolved_type = judge_api_type(base_url, api_type)
    return {
        "JUDGE_MODEL": str(cfg.get("model", judge_model)),
        "JUDGE_BASE_URL": base_url,
        "JUDGE_API_TYPE": resolved_type,
        "JUDGE_API_KEY": str(api_key),
    }


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_task_toml(
    case: str,
    task: dict[str, Any],
    *,
    time_limit_s: int,
    no_judge: bool,
    judge_env: dict[str, str],
) -> str:
    """Render task.toml for a ClawBench case (Harbor schema version 1.0)."""
    metadata = task.get("metadata") or {}
    description = str(metadata.get("description") or task.get("instruction", ""))[:300]
    name = f"clawbench/{_sanitize_name(case)}"

    lines: list[str] = [
        'version = "1.0"',
        "",
        "[task]",
        f'name = "{_toml_escape(name)}"',
        f'description = "{_toml_escape(description)}"',
        'keywords = ["clawbench", "web-agent", "browser"]',
        "",
        "[metadata]",
        f'clawbench_case = "{_toml_escape(case)}"',
        f"clawbench_time_limit_min = {task.get('time_limit')}",
        f"clawbench_no_judge = {str(no_judge).lower()}",
        "clawbench_eval_schema = "
        + json.dumps(json.dumps(task.get("eval_schema", {}), ensure_ascii=True)),
    ]
    for key in ("task_id", "metaclass", "class", "platform"):
        if key in metadata:
            val = metadata[key]
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                lines.append(f"clawbench_{key} = {val}")
            else:
                lines.append(f'clawbench_{key} = "{_toml_escape(str(val))}"')

    # Verifier: shared environment (default) so it sees /data/interception.json.
    lines += [
        "",
        "[verifier]",
        f"timeout_sec = {float(max(time_limit_s, 120) + 300)}",
    ]
    verifier_env: dict[str, str] = {}
    if not no_judge:
        verifier_env.update(judge_env)
    if verifier_env:
        lines.append("")
        lines.append("[verifier.env]")
        for k, v in verifier_env.items():
            lines.append(f'{k} = "{_toml_escape(v)}"')

    lines += [
        "",
        "[agent]",
        f"timeout_sec = {float(time_limit_s)}",
        "",
        "[environment]",
        "build_timeout_sec = 1800.0",
        'network_mode = "public"',
    ]
    return "\n".join(lines) + "\n"


def build_dockerfile(base_image: str) -> str:
    """Render environment/Dockerfile: bake the per-task eval schema + persona."""
    return (
        f"# ClawBench task environment (Harbor-as-runner).\n"
        f"FROM {base_image}\n\n"
        "# The interceptor reads /eval-schema.json to decide Stage-1 matches.\n"
        "COPY eval-schema.json /eval-schema.json\n\n"
        "# Bake the fixed persona bundle; the agent copies it to /my-info at run.\n"
        "COPY my-info /clawbench/my-info\n\n"
        "# The task instruction (for the judge fallback when INSTRUCTION is unset).\n"
        "COPY instruction.txt /clawbench/instruction.txt\n"
    )


def build_test_sh(no_judge: bool) -> str:
    """Render tests/test.sh: the Harbor verifier that writes reward.txt."""
    no_judge_flag = " --no-judge" if no_judge else ""
    return (
        "#!/bin/bash\n"
        "# Harbor verifier for a ClawBench task. Reuses ClawBench's pure-Python\n"
        "# Stage-1 (+ optional Stage-2 judge) scoring and writes the reward to\n"
        "# /logs/verifier/reward.txt (Harbor's reward file).\n"
        "set -uo pipefail\n"
        "mkdir -p /logs/verifier\n"
        f"python3 -m clawbench.harbor.verify{no_judge_flag} "
        "|| echo 0.0 > /logs/verifier/reward.txt\n"
    )


def export_case(
    case_dir: Path,
    out_dir: Path,
    *,
    base_image: str,
    no_judge: bool,
    judge_env: dict[str, str],
) -> tuple[bool, str]:
    """Export one case. Returns (exported, message)."""
    task_file = case_dir / "task.json"
    if not task_file.exists():
        return False, f"no task.json in {case_dir}"
    try:
        task = validate_task_data(json.loads(task_file.read_text()), task_file)
    except (json.JSONDecodeError, ValueError) as e:
        return False, f"invalid task.json: {e}"

    skip, reason = needs_email_or_signup(task)
    if skip:
        return False, f"SKIP {reason}"

    case = case_dir.name
    time_limit_s = int(float(task["time_limit"]) * 60)

    dst = out_dir / case
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "environment").mkdir(parents=True)
    (dst / "tests").mkdir(parents=True)

    # task.toml
    (dst / "task.toml").write_text(
        build_task_toml(
            case,
            task,
            time_limit_s=time_limit_s,
            no_judge=no_judge,
            judge_env=judge_env,
        )
    )
    # instruction.md (+ a plain instruction.txt baked for the judge fallback)
    instruction = build_instruction(task)
    (dst / "instruction.md").write_text(instruction)
    (dst / "environment" / "instruction.txt").write_text(
        str(task.get("instruction", ""))
    )
    # environment/eval-schema.json
    (dst / "environment" / "eval-schema.json").write_text(
        json.dumps(task["eval_schema"], indent=2)
    )
    # environment/Dockerfile
    (dst / "environment" / "Dockerfile").write_text(build_dockerfile(base_image))
    # environment/my-info (fixed persona)
    my_info = dst / "environment" / "my-info"
    my_info.mkdir()
    persona_src = SHARED_ROOT / "alex_green_personal_info.json"
    if persona_src.exists():
        shutil.copy2(persona_src, my_info / "alex_green_personal_info.json")
    # tests/test.sh
    test_sh = dst / "tests" / "test.sh"
    test_sh.write_text(build_test_sh(no_judge))
    test_sh.chmod(0o755)

    return True, f"exported -> {dst}"


def _iter_cases(src: Path) -> list[Path]:
    if (src / "task.json").exists():
        return [src]
    return sorted(p for p in src.iterdir() if (p / "task.json").exists())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export ClawBench v2 tasks to Harbor task directories."
    )
    parser.add_argument(
        "src",
        type=Path,
        help="A ClawBench case dir, or a parent dir of case dirs (e.g. test-cases/v2).",
    )
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        required=True,
        help="Output directory for the Harbor task dir(s).",
    )
    parser.add_argument(
        "--base-image",
        default=DEFAULT_BASE_IMAGE,
        help=f"Services-mode base image for environment/Dockerfile (default: {DEFAULT_BASE_IMAGE}).",
    )
    parser.add_argument(
        "--judge",
        default=DEFAULT_JUDGE_MODEL,
        help=f"Judge model key in models.yaml (default: {DEFAULT_JUDGE_MODEL}).",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Export Stage-1-only tasks (reward = intercepted).",
    )
    parser.add_argument(
        "--models-yaml",
        type=Path,
        default=None,
        help="Path to models.yaml for resolving the judge (default: workspace).",
    )
    args = parser.parse_args(argv)

    judge_env = {} if args.no_judge else _load_judge_env(args.judge, args.models_yaml)

    cases = _iter_cases(args.src)
    if not cases:
        print(f"ERROR: no task.json found under {args.src}")
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    exported: list[str] = []
    skipped: list[tuple[str, str]] = []
    for case_dir in cases:
        ok, msg = export_case(
            case_dir,
            args.out,
            base_image=args.base_image,
            no_judge=args.no_judge,
            judge_env=judge_env,
        )
        if ok:
            exported.append(case_dir.name)
            print(f"  [ok]   {case_dir.name}: {msg}")
        else:
            skipped.append((case_dir.name, msg))
            print(f"  [skip] {case_dir.name}: {msg}")

    if skipped:
        skipped_md = args.out / "SKIPPED.md"
        lines = ["# Skipped cases (Harbor export)\n"]
        for name, msg in skipped:
            lines.append(f"- `{name}`: {msg}")
        skipped_md.write_text("\n".join(lines) + "\n")

    print(f"\nExported {len(exported)} task(s), skipped {len(skipped)} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
