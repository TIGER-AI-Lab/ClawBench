"""Export ClawBench v2 tasks to Harbor task directories (``clawbench-export-harbor``).

A Harbor task directory has the canonical shape::

    <case>/
      task.toml             # version + [metadata] + [verifier]/[agent] + [environment].docker_image
      instruction.md        # the task prompt (reuses run_support.task.build_instruction)
      environment/
        docker-compose.yaml # PREBUILT mode: image: ${PREBUILT_IMAGE_NAME} + bind mounts
        eval-schema.json    # the interceptor's match schema (bind-mounted to /eval-schema.json)
        instruction.txt     # plain instruction (bind-mounted to /clawbench/instruction.txt)
        my-info/...         # the fixed persona bundle (bind-mounted to /clawbench/my-info)
      tests/
        test.sh             # the verifier: python -m clawbench.harbor.verify

PREBUILT mode (no ``docker compose build``): ``[environment].docker_image`` points
at the already-built ``localhost/clawbench-harbor-task`` podman image, so Harbor
selects ``docker-compose-prebuilt.yaml`` (``image: ${PREBUILT_IMAGE_NAME}`` +
``command: sleep infinity``) instead of booting an isolated BuildKit container that
cannot see podman's local images. Because there is no build layer, the per-task
files are delivered at runtime via **bind mounts** declared in the task's own
``environment/docker-compose.yaml`` (relative paths resolve against the staged
``environment/`` dir). The interceptor reads ``/eval-schema.json`` at service
startup, so it must be present at container creation — a mount guarantees that.

Harbor runs it with (NO ``--agent`` flag — that is invalid with
``--agent-import-path``, which only accepts registry enum values). The judge API
key is NOT baked into ``task.toml`` (a shareable artifact); inject it at runtime
with ``--ve JUDGE_API_KEY=...`` when judging is enabled::

    harbor run --path <out>/<case> \\
      --agent-import-path clawbench.harbor.agent:ClawbenchHarnessAgent \\
      --ak harness=harbor --ak api_key=<GEMINI_KEY> \\
      --ve JUDGE_API_KEY=<JUDGE_KEY> \\
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

from clawbench.harbor.constants import HARNESS_CLEANUP_GRACE_S
from clawbench.harbor.model_map import judge_api_type
from clawbench.runner.run_support.task import (
    BUILTIN_MY_INFO_FILES,
    build_instruction,
    copy_extra_info,
    normalize_extra_info,
    prepare_personal_info,
    validate_task_data,
)
from clawbench.utils.paths import SHARED_ROOT

# Prebuilt image used as ``[environment].docker_image``. The ``localhost/`` prefix
# is the podman local-registry namespace, so Harbor's ``docker inspect`` resolves
# it without ever attempting a remote pull (which is what BuildKit did before).
DEFAULT_BASE_IMAGE = "localhost/clawbench-harbor-task:latest"
DEFAULT_JUDGE_MODEL = "gemini-3.5-flash"

# Harbor bakes a *fixed* persona (no per-run disposable inbox; signup / email-
# verification tasks are skipped upstream by needs_email_or_signup()). This seeds
# the generated email_credentials.json so the staged my-info bundle is self-
# consistent and matches the instruction's file list. It is a placeholder, never a
# live credential, and is never used for real authentication.
HARBOR_PERSONA_FALLBACK_EMAIL = "alex.green.uoft@clawbench.cc"
HARBOR_PERSONA_PASSWORD = "ClawBench-Harbor-Demo-Pw"


def _persona_email() -> str:
    """Email seeded into the baked persona bundle (email_credentials/personal_info).

    Reuses the shared persona's own contact email so the staged my-info files stay
    self-consistent: prepare_personal_info() overwrites contact.email with this, so
    passing the existing value round-trips. Falls back to a constant if unreadable.
    """
    src = SHARED_ROOT / "alex_green_personal_info.json"
    try:
        data = json.loads(src.read_text())
    except (OSError, json.JSONDecodeError):
        return HARBOR_PERSONA_FALLBACK_EMAIL
    email = (data.get("contact") or {}).get("email") if isinstance(data, dict) else None
    if isinstance(email, str) and email.strip():
        return email.strip()
    return HARBOR_PERSONA_FALLBACK_EMAIL


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
    """Escape a string for a TOML basic ("...") string.

    No TOML writer is vendored, so render escapes by hand. TOML basic strings
    forbid raw control characters: backslash and double-quote take their
    short escapes, the common control chars get ``\\n``/``\\r``/``\\t``/``\\b``/``\\f``,
    and any other control char (U+0000..U+001F, U+007F) becomes a ``\\uXXXX``
    escape -- otherwise a multiline/control-char description yields invalid TOML.
    """
    short = {
        "\\": "\\\\",
        '"': '\\"',
        "\b": "\\b",
        "\t": "\\t",
        "\n": "\\n",
        "\f": "\\f",
        "\r": "\\r",
    }
    out: list[str] = []
    for ch in value:
        if ch in short:
            out.append(short[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return "".join(out)


def build_task_toml(
    case: str,
    task: dict[str, Any],
    *,
    time_limit_s: int,
    no_judge: bool,
    judge_env: dict[str, str],
    base_image: str,
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
        # task.toml is a *shareable* artifact, so no secrets may be baked in. Only
        # the non-secret judge config (model/base_url/api_type) goes into
        # [verifier.env]; JUDGE_API_KEY must reach the verifier at runtime via
        # ``harbor run --ve JUDGE_API_KEY=...`` (see clawbench.harbor.verify and
        # clawbench.harbor.parity).
        verifier_env.update(
            {k: v for k, v in judge_env.items() if k != "JUDGE_API_KEY"}
        )
        # Forward the task's judge_context so Harbor judging matches native (the
        # native runner passes task["judge_context"] to judge_request, see
        # runner.run). It is task data (not a secret) like eval_schema, so it is
        # safe to bake into the shareable task.toml. verify.py reads JUDGE_CONTEXT
        # from the verifier env and passes it to judge_request(judge_context=...).
        judge_context = task.get("judge_context")
        if isinstance(judge_context, dict) and judge_context:
            verifier_env["JUDGE_CONTEXT"] = json.dumps(judge_context, ensure_ascii=True)
    if verifier_env:
        lines.append("")
        lines.append("[verifier.env]")
        for k, v in verifier_env.items():
            lines.append(f'{k} = "{_toml_escape(v)}"')

    # PREBUILT mode: pointing [environment].docker_image at the already-built
    # local image makes Harbor pick docker-compose-prebuilt.yaml (no build). With
    # no environment/Dockerfile present, should_use_prebuilt_docker_image() returns
    # True, and PREBUILT_IMAGE_NAME is set from this value. The per-task files are
    # delivered by the bind mounts in environment/docker-compose.yaml instead of a
    # COPY build layer.
    # Outer Harbor agent timeout: the harness self-stops at TIME_LIMIT_S then needs
    # ~20s of mandatory cleanup (transcript/recording/reward). If Harbor's own
    # [agent].timeout_sec equalled the raw limit it would kill the agent mid-cleanup
    # -> the verifier never runs and the trial errors with no reward. Add the same
    # cleanup grace the agent's exec() timeout uses (clawbench.harbor.agent).
    lines += [
        "",
        "[agent]",
        f"timeout_sec = {float(time_limit_s + HARNESS_CLEANUP_GRACE_S)}",
        "",
        "[environment]",
        f'docker_image = "{_toml_escape(base_image)}"',
        "build_timeout_sec = 1800.0",
        'network_mode = "public"',
    ]
    return "\n".join(lines) + "\n"


def build_compose(time_limit_s: int) -> str:
    """Render environment/docker-compose.yaml for PREBUILT mode (no build).

    Layered *after* Harbor's docker-compose-prebuilt.yaml (which already sets
    ``image: ${PREBUILT_IMAGE_NAME}`` and ``command: sleep infinity``), so this
    file only needs to add the per-task bind mounts that a COPY build layer used
    to provide. ``pull_policy: never`` keeps compose from attempting a remote pull
    for the local-only image. Relative sources resolve against the staged
    ``environment/`` dir (Harbor's compose ``--project-directory``).

    The ``environment:`` block bakes the task's real time limit into the container
    as ``CLAWBENCH_TIME_LIMIT_S``. This is the self-contained channel for the
    limit: ``docker compose exec`` (how the agent runs ``/run-harness.sh``)
    inherits the container's ``environment``, so run-harbor.sh reads the real limit
    instead of falling back to its 1800s default -- even for a standalone
    ``harbor run`` where the agent received no ``time_limit_s`` kwarg. ([agent].env
    and [environment].env do NOT reach exec'd commands, so a mount-style env var is
    the only reliable in-container delivery.)

    Mounts:
      * eval-schema.json -> /eval-schema.json   (interceptor reads at startup)
      * instruction.txt  -> /clawbench/instruction.txt (judge fallback)
      * my-info          -> /clawbench/my-info  (agent copies to /my-info at run)
    """
    return (
        "# ClawBench task environment (Harbor-as-runner, PREBUILT mode).\n"
        "# No build: uses the local image via docker-compose-prebuilt.yaml; this\n"
        "# overlay only adds the per-task bind mounts the interceptor + agent need.\n"
        "services:\n"
        "  main:\n"
        "    pull_policy: never\n"
        "    environment:\n"
        # Quoted so YAML keeps it a string; run-harbor.sh reads it via
        # ${TIME_LIMIT_S:-${CLAWBENCH_TIME_LIMIT_S:-1800}}.
        f'      CLAWBENCH_TIME_LIMIT_S: "{int(time_limit_s)}"\n'
        "    volumes:\n"
        "      - ./eval-schema.json:/eval-schema.json:ro\n"
        "      - ./instruction.txt:/clawbench/instruction.txt:ro\n"
        "      - ./my-info:/clawbench/my-info:ro\n"
    )


def build_test_sh(no_judge: bool) -> str:
    """Render tests/test.sh: the Harbor verifier that writes reward.json/reward.txt.

    On a *clean* run, ``clawbench.harbor.verify`` writes reward.json, reward.txt and
    a rich verify-result.json itself. If the verifier process crashes before doing
    so (import error, OOM, segfault, ...), the fallback here writes a zero reward AND
    a minimal ``verify-result.json`` carrying the captured stderr, so a verifier
    crash is diagnosable instead of silently scoring 0.0 with no explanation.
    """
    no_judge_flag = " --no-judge" if no_judge else ""
    # Inline diagnostic writer: read the captured stderr and emit a minimal
    # verify-result.json. Single-quoted heredoc => no bash expansion in the body.
    diag = (
        "import json\n"
        "from pathlib import Path\n"
        "try:\n"
        "    err = Path('/logs/verifier/verify-stderr.log').read_text(errors='replace')\n"
        "except OSError:\n"
        "    err = ''\n"
        "err = err.strip()[-4000:] or 'verifier crashed before writing a result'\n"
        "Path('/logs/verifier/verify-result.json').write_text(\n"
        "    json.dumps({'pass': False, 'reward': 0.0, 'error': err})\n"
        ")\n"
    )
    return (
        "#!/bin/bash\n"
        "# Harbor verifier for a ClawBench task. Reuses ClawBench's pure-Python\n"
        "# Stage-1 (+ optional Stage-2 judge) scoring and writes the reward to\n"
        "# /logs/verifier/reward.json (canonical) and reward.txt (fallback).\n"
        "set -uo pipefail\n"
        "mkdir -p /logs/verifier\n"
        f"if ! python3 -m clawbench.harbor.verify{no_judge_flag} "
        "2> /logs/verifier/verify-stderr.log; then\n"
        "  cat /logs/verifier/verify-stderr.log >&2 || true\n"
        "  echo '{\"reward\": 0.0}' > /logs/verifier/reward.json\n"
        "  echo 0.0 > /logs/verifier/reward.txt\n"
        "  python3 - <<'PYEOF' || printf '%s' "
        '\'{"pass": false, "reward": 0.0, '
        '"error": "verifier crashed before writing a result"}\' '
        "> /logs/verifier/verify-result.json\n"
        f"{diag}"
        "PYEOF\n"
        "fi\n"
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
            base_image=base_image,
        )
    )
    env_dir = dst / "environment"
    # environment/instruction.txt (plain instruction, bind-mounted for judge fallback)
    (env_dir / "instruction.txt").write_text(str(task.get("instruction", "")))
    # environment/eval-schema.json (bind-mounted to /eval-schema.json)
    (env_dir / "eval-schema.json").write_text(json.dumps(task["eval_schema"], indent=2))
    # environment/docker-compose.yaml (PREBUILT mode: bind mounts + baked time
    # limit, no build)
    (env_dir / "docker-compose.yaml").write_text(build_compose(time_limit_s))

    # environment/my-info: stage the *full* canonical persona bundle exactly as the
    # native runner does. prepare_personal_info() is the single source of all three
    # built-in files build_instruction() advertises (alex_green_personal_info.json,
    # email_credentials.json, alex_green_resume.pdf) -- earlier we only baked
    # personal_info.json, so the prompt pointed at two missing files. Harbor has no
    # per-run disposable inbox, so we bake a fixed persona email/password.
    my_info = env_dir / "my-info"
    persona_tmp, _ = prepare_personal_info(
        SHARED_ROOT, _persona_email(), HARBOR_PERSONA_PASSWORD, env_dir
    )
    persona_tmp.rename(my_info)
    # Also stage every extra_info file the task references (warns-only on miss).
    copy_warnings = copy_extra_info(task, case_dir, my_info)

    # Make the instruction advertise ONLY the built-in files we actually staged: a
    # built-in that genuinely can't be produced (e.g. resume-PDF generation fails)
    # is dropped from the prompt rather than shipped as a dangling reference.
    staged_builtins = [
        (name, desc)
        for name, desc in BUILTIN_MY_INFO_FILES
        if (my_info / name).is_file()
    ]
    instruction = build_instruction(task, builtin_files=staged_builtins)

    # Hard-fail guard (M4): every file the instruction references under /my-info/
    # must exist in the staged bundle before we write the archive. Built-ins are
    # already filtered to staged_builtins, so this also catches extra_info files
    # that copy_extra_info() only warned about (otherwise a silent prompt/data bug).
    extra_entries, _ = normalize_extra_info(task.get("extra_info"))
    referenced = [name for name, _ in staged_builtins]
    referenced += [Path(e["path"]).name for e in extra_entries if e.get("path")]
    missing = sorted({name for name in referenced if not (my_info / name).is_file()})
    if missing:
        shutil.rmtree(dst, ignore_errors=True)
        raise RuntimeError(
            f"{case}: file(s) referenced by the instruction are missing from "
            f"my-info: {', '.join(missing)}. "
            f"copy_extra_info warnings: {copy_warnings or 'none'}"
        )

    # instruction.md (depends on which built-ins were staged above)
    (dst / "instruction.md").write_text(instruction)

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
        help="Prebuilt services-mode image set as [environment].docker_image "
        f"(default: {DEFAULT_BASE_IMAGE}). Must already exist locally; PREBUILT "
        "mode never pulls it.",
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
    if not args.no_judge:
        print(
            "NOTE: the judge API key is NOT baked into task.toml (shareable "
            "artifact). Pass it at runtime: harbor run ... --ve JUDGE_API_KEY=<key>"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
