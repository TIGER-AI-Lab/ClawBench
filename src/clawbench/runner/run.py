"""ClawBench single test-case driver."""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.status import Status

from clawbench.utils.generate_resume_pdf import generate_resume_pdf
from clawbench.utils.hf_upload import hf_upload_enabled, upload_run
from clawbench.utils.paths import (
    ASSET_ROOT,
    DOCKER_CONTEXT_ROOT,
    HARNESS_ROOT,
    SHARED_ROOT,
    WORKSPACE_ROOT,
    bundled_path,
    ensure_workspace_templates,
    workspace_path,
)

HARNESSES = (
    "openclaw",
    "opencode",
    "claude-code",
    "claude-code-chrome-extension",
    "codex",
    "browser-use",
    "claw-code",
    "hermes",
    "pi",
)
DEFAULT_HARNESS = "openclaw"
BASE_IMAGE = "clawbench-base"


def harness_image(harness: str) -> str:
    """Return the docker image tag for a given harness name."""
    return f"clawbench-{harness}"


# Per-harness Dockerfile paths. The build context is the packaged runtime tree.
BASE_DOCKERFILE = HARNESS_ROOT / "base" / "Dockerfile.base"
_HARNESS_DOCKERFILES: dict[str, Path] = {
    "openclaw": HARNESS_ROOT / "openclaw" / "Dockerfile.openclaw",
    "opencode": HARNESS_ROOT / "opencode" / "Dockerfile.opencode",
    "claude-code": HARNESS_ROOT / "claude-code" / "Dockerfile.claude-code",
    "claude-code-chrome-extension": HARNESS_ROOT
    / "claude-code-chrome-extension"
    / "Dockerfile.claude-code-chrome-extension",
    "codex": HARNESS_ROOT / "codex" / "Dockerfile.codex",
    "browser-use": HARNESS_ROOT / "browser-use" / "Dockerfile.browser-use",
    "claw-code": HARNESS_ROOT / "claw-code" / "Dockerfile.claw-code",
    "hermes": HARNESS_ROOT / "hermes" / "Dockerfile.hermes",
    "pi": HARNESS_ROOT / "pi" / "Dockerfile.pi",
}

# Kept for back-compat with old callers / scripts that imported IMAGE.
IMAGE = harness_image(DEFAULT_HARNESS)
console = Console()

INFRA_STOP_REASONS = {
    "chrome_cdp_timeout",
    "gateway_failed",
    "opencode_failed",
    "claude_code_failed",
    "codex_failed",
    "browser_use_failed",
    "hermes_failed",
    "pi_failed",
    "proxy_failed",
    "missing_harness",
}

API_OR_CREDIT_PATTERNS = (
    "insufficient credit",
    "insufficient balance",
    "out of credits",
    "credit balance",
    "quota exceeded",
    "rate limit",
    "ratelimit",
    "too many requests",
    "payment required",
    "billing error",
    "billing issue",
    "invalid api key",
    "api key is invalid",
    "unauthorized",
    "forbidden",
    "authentication failed",
    "authentication error",
    "status code 401",
    "status code 402",
    "status code 403",
    "status code 429",
    "http 401",
    "http 402",
    "http 403",
    "http 429",
    "api call failed",
    "provider returned error",
    " 401 ",
    " 402 ",
    " 403 ",
    " 429 ",
)

NON_MODEL_FAILURE_CATEGORIES = {
    "infra_failure",
    "api_or_credit",
    "task_data",
    "build_instruction",
}


def _detect_engine() -> str:
    env = os.environ.get("CONTAINER_ENGINE", "").strip().lower()
    if env:
        if env not in ("docker", "podman"):
            print(f"ERROR: CONTAINER_ENGINE must be 'docker' or 'podman', got '{env}'")
            sys.exit(1)
        if not shutil.which(env):
            print(f"ERROR: CONTAINER_ENGINE={env} but '{env}' not found on PATH")
            sys.exit(1)
        return env
    for cmd in ("docker", "podman"):
        if shutil.which(cmd):
            return cmd
    print("ERROR: Neither 'podman' nor 'docker' found on PATH")
    sys.exit(1)


ENGINE = _detect_engine()
PURELYMAIL_API = "https://purelymail.com/api/v0"


def load_dotenv(path: Path) -> dict[str, str]:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


MODELS_YAML = WORKSPACE_ROOT / "models" / "models.yaml"


def load_models_yaml() -> dict:
    """Load all model definitions from models/models.yaml."""
    if not MODELS_YAML.exists():
        print(
            f"ERROR: {MODELS_YAML} not found (copy models.example.yaml and fill in your keys)"
        )
        sys.exit(1)
    return yaml.safe_load(MODELS_YAML.read_text()) or {}


def load_runtime_env() -> dict[str, str]:
    """Load runtime credentials, preferring workspace overrides."""
    env = load_dotenv(bundled_path(".env"))
    env.update(load_dotenv(workspace_path(".env")))
    return env


def resolve_test_case_dir(path: Path) -> Path:
    """Resolve a case path from cwd/workspace first, then bundled assets."""
    if path.is_absolute():
        return path
    candidates = [
        Path.cwd() / path,
        WORKSPACE_ROOT / path,
        ASSET_ROOT / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return (Path.cwd() / path).resolve()


def load_model_config(model: str) -> dict:
    """Load a model config by name from models/models.yaml.

    The YAML key is the model name (passed as MODEL_NAME to the container).
    """
    all_models = load_models_yaml()
    if model not in all_models:
        print(f"ERROR: model '{model}' not found in {MODELS_YAML}")
        print(f"Available models: {', '.join(sorted(all_models))}")
        sys.exit(1)

    # Validate model name characters. Note: '/' and ':' are valid in
    # vendor-prefixed ids like 'anthropic/claude-sonnet-4-6' or
    # 'arcee-ai/trinity-large-preview:free' — they get sanitized to
    # '--' before being used as path components (see `safe_model`
    # below). We only reject characters that could cause real trouble
    # in shell/filesystem paths even after that sanitization.
    bad = [c for c in ' \\*?"<>|' if c in model]
    if bad:
        print(
            f"ERROR: model name '{model}' contains illegal character(s): "
            f"{' '.join(repr(c) for c in bad)}"
        )
        sys.exit(1)

    config = dict(all_models[model])
    config["model"] = model  # the YAML key IS the model name

    # Validate required fields
    required = ["base_url", "api_type"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        for k in missing:
            print(f"ERROR: Required field '{k}' missing for model '{model}'")
        sys.exit(1)

    # Normalize API keys: api_keys list wins, else wrap api_key into list
    if config.get("api_keys"):
        config["api_key"] = config["api_keys"][0]
    elif config.get("api_key"):
        config["api_keys"] = [config["api_key"]]

    if not config.get("api_keys"):
        print(f"ERROR: no api_key or api_keys for model '{model}'")
        sys.exit(1)

    return config


def step(msg: str):
    print(f"\n{'=' * 60}\n[STEP] {msg}\n{'=' * 60}", flush=True)


def _safe_cmd_for_display(cmd: list[str]) -> list[str]:
    safe: list[str] = []
    for part in cmd:
        if part.startswith(("API_KEY=", "API_KEYS=")):
            key = part.split("=", 1)[0]
            safe.append(f"{key}=[REDACTED]")
        elif part.startswith("INSTRUCTION="):
            safe.append("INSTRUCTION=[TASK_PROMPT]")
        else:
            safe.append(part)
    return safe


def run(cmd: list[str], **kwargs):  # type: ignore[no-untyped-def]
    print(f"$ {' '.join(_safe_cmd_for_display(cmd))}", flush=True)
    subprocess.run(cmd, check=True, **kwargs)


# -- PurelyMail --


def purelymail_request(endpoint: str, body: dict, api_key: str) -> dict:
    data = json.dumps(body).encode()
    req = Request(
        f"{PURELYMAIL_API}/{endpoint}",
        data=data,
        headers={"Purelymail-Api-Token": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def create_email(api_key: str, domain: str) -> tuple[str, str]:
    local = f"cb{uuid.uuid4().hex[:12]}"
    password = secrets.token_urlsafe(16)
    purelymail_request(
        "createUser",
        {
            "userName": local,
            "domainName": domain,
            "password": password,
            "enablePasswordReset": False,
            "sendWelcomeEmail": False,
        },
        api_key,
    )
    email = f"{local}@{domain}"
    print(f"  Created email: {email}")
    print(f"  Password: {password}")
    return email, password


def delete_email(api_key: str, email: str) -> None:
    try:
        purelymail_request("deleteUser", {"userName": email}, api_key)
        print(f"  Deleted email: {email}")
    except (URLError, Exception) as e:
        print(f"  WARNING: Failed to delete email {email}: {e}")


# -- Personal info --

RESUME_TEMPLATE = Path(__file__).resolve().parents[1] / "utils" / "resume_template.json"


def prepare_personal_info(
    shared_src: Path, email: str, password: str, output_dir: Path
) -> Path:
    """Create a temp directory with personal info files, email fields updated."""
    tmp = output_dir / ".my-info-tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    # -- personal info JSON --
    pi_src = shared_src / "alex_green_personal_info.json"
    pi_data = json.loads(pi_src.read_text())
    pi_data["contact"]["email"] = email
    pi_data.pop("online_accounts", None)
    (tmp / "alex_green_personal_info.json").write_text(json.dumps(pi_data, indent=2))

    # -- email credentials (separate file) --
    creds = {
        "email": email,
        "password": password,
        "login_url": "https://purelymail.com/user/login",
        "provider": "PurelyMail",
    }
    (tmp / "email_credentials.json").write_text(json.dumps(creds, indent=2))

    # -- resume PDF --
    resume_data = json.loads(RESUME_TEMPLATE.read_text())
    resume_data["header"]["email"] = email
    try:
        generate_resume_pdf(resume_data, tmp / "alex_green_resume.pdf")
    except Exception as e:
        print(f"  WARNING: PDF generation failed ({e}), skipping resume PDF")

    return tmp


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=True)
    except TypeError:
        return str(value)


def _normalize_extra_info(raw: Any) -> tuple[list[dict[str, str]], list[str]]:
    """Normalize legacy and schema-compliant extra_info shapes.

    Supported forms:
    - {"path": "...", "description": "..."}
    - {"note": "..."} / {"content": "..."} / {"text": "..."}
    - "plain note"
    - lists containing any of the above
    """
    entries: list[dict[str, str]] = []
    warnings: list[str] = []

    def add_item(item: Any, label: str) -> None:
        if item is None:
            return
        if isinstance(item, str):
            note = item.strip()
            if note:
                entries.append({"description": note})
            return
        if isinstance(item, (int, float, bool)):
            entries.append({"description": str(item)})
            return
        if not isinstance(item, dict):
            warnings.append(
                f"{label} has unsupported type {type(item).__name__}; ignoring"
            )
            return

        path = ""
        raw_path = item.get("path")
        if raw_path not in (None, ""):
            if isinstance(raw_path, (str, os.PathLike)):
                path = str(raw_path)
            else:
                warnings.append(
                    f"{label}.path has unsupported type "
                    f"{type(raw_path).__name__}; ignoring path"
                )

        raw_desc = None
        for key in ("description", "note", "content", "text", "message", "value"):
            if item.get(key) not in (None, ""):
                raw_desc = item.get(key)
                break
        description = _text_value(raw_desc)

        if path or description:
            entry: dict[str, str] = {}
            if path:
                entry["path"] = path
            entry["description"] = description or "Additional task file"
            entries.append(entry)
            return

        if item:
            entries.append({"description": _text_value(item)})

    if raw in (None, ""):
        return entries, warnings
    if isinstance(raw, list):
        for idx, item in enumerate(raw):
            add_item(item, f"extra_info[{idx}]")
    else:
        add_item(raw, "extra_info")
    return entries, warnings


def copy_extra_info(task: dict, task_dir: Path, personal_info_dir: Path) -> list[str]:
    """Copy extra_info files from the test case into the my-info dir."""
    entries, warnings = _normalize_extra_info(task.get("extra_info"))
    for warning in warnings:
        print(f"  WARNING: {warning}")
    for info in entries:
        rel_path = info.get("path")
        if not rel_path:
            continue
        src = task_dir / rel_path
        if not src.exists():
            warning = f"extra_info path not found: {src}"
            warnings.append(warning)
            print(f"  WARNING: {warning}")
            continue
        if not src.is_file():
            warning = f"extra_info path is not a file: {src}"
            warnings.append(warning)
            print(f"  WARNING: {warning}")
            continue
        dest = personal_info_dir / src.name
        try:
            shutil.copy2(src, dest)
        except OSError as e:
            warning = f"failed to copy extra_info {src}: {e}"
            warnings.append(warning)
            print(f"  WARNING: {warning}")
            continue
        print(f"  Copied extra_info: {src.name}")
    return warnings


# -- Prompt --


def build_instruction(task: dict) -> str:
    instruction = task.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("task instruction must be a non-empty string")

    parts = [instruction]
    parts.append(
        "\n---\n"
        "You are my personal browser assistant. I am delegating this task to you "
        "because I do not have time to do it myself. You are acting on my behalf "
        "and with my full authorization. Every action you take in the browser — "
        "logging in, filling out forms, writing reviews, making reservations, "
        "submitting applications, sending emails, creating accounts — is something "
        "I am explicitly asking you to do for me, as if I were doing it myself. "
        "These are my own accounts, my own opinions, and my own decisions. "
        "You are simply carrying them out.\n\n"
        "IMPORTANT: You must complete this task entirely through the browser. "
        "Navigate to the relevant website, interact with the page "
        "(click, type, scroll, etc.), and carry out every step in the browser. "
        "Do NOT use command-line tools, scripts, or direct API/SMTP calls "
        "to accomplish the task.\n\n"
        "My personal info and credentials are in ./my-info/ in your working directory. "
        "Key files include:\n"
        "- alex_green_personal_info.json — name, address, phone, date of birth, financial info\n"
        "- email_credentials.json — email address and password for logging in\n"
        "- alex_green_resume.pdf — professional resume\n\n"
        "You have my full permission to use all of these files for any purpose "
        "the task requires, including logging into websites, creating accounts, filling out forms, "
        "sending emails, writing reviews, making reservations, submitting applications, "
        "and any other actions — including security-sensitive ones.\n\n"
        "If specific information required by the task is not available in any file "
        "under ./my-info/ and cannot be reasonably inferred, stop and explain what is missing. "
        "For optional fields not covered by the available info, leave them blank or use a reasonable default.\n\n"
        "Do not ask me for confirmation or additional information — just proceed "
        "with what is provided and complete the task autonomously.\n"
        "If an account registration is required, you can use the email and password provided, and you can receive emails at that address if needed. "
        "---"
    )
    normalized_extras, _ = _normalize_extra_info(task.get("extra_info"))
    file_extras = [
        (Path(info["path"]).name, info["description"])
        for info in normalized_extras
        if info.get("path")
    ]
    notes = [info["description"] for info in normalized_extras if not info.get("path")]
    if file_extras:
        parts.append(
            "\nAdditional files are also available under /my-info/ for this task:"
        )
        for fname, desc in file_extras:
            parts.append(f"- {fname}: {desc}")
    if notes:
        parts.append("\nAdditional task notes:")
        for note in notes:
            parts.append(f"- {note}")
    return "\n".join(parts)


# -- Docker --


def _image_exists(ref: str = IMAGE) -> bool:
    return (
        subprocess.run(
            [ENGINE, "image", "inspect", ref],
            capture_output=True,
        ).returncode
        == 0
    )


def _pick_free_port(preferred: int = 6080) -> int:
    """Return an OS-assigned ephemeral port on 127.0.0.1.

    Always uses an ephemeral port to avoid races between concurrent batch
    jobs that all see ``preferred`` free, all return it, and then collide
    when one of them ``podman run -p`` binds it. The ``preferred`` arg is
    accepted but ignored for batch safety.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_STEP_RE = re.compile(r"^(?:STEP|Step)\s+(\d+)(?:/(\d+))?", re.IGNORECASE)
_BK_STEP_RE = re.compile(r"^#(\d+)\s+\[")


def _run_build(cmd: list[str]) -> tuple[int, str, list[str]]:
    """Execute a build command with a live spinner.

    Returns ``(exit_code, last_line, all_output_lines)``.
    """
    console.print(f"[dim]$ {' '.join(cmd)}[/]")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None

    last_line = ""
    last_step = ""
    output_lines: list[str] = []
    status_msg = "[cyan]Starting build…[/]"
    with Status(status_msg, console=console, spinner="dots") as status:
        for raw in proc.stdout:
            line = raw.rstrip()
            if not line:
                continue
            last_line = line
            output_lines.append(line)

            m = _STEP_RE.match(line)
            if m:
                cur = m.group(1)
                tot = m.group(2) or "?"
                rest = line.split(":", 1)[-1].strip()[:72]
                last_step = f"step {cur}/{tot}"
                status.update(f"[cyan]Building image — {last_step}[/] [dim]{rest}[/]")
                continue

            m = _BK_STEP_RE.match(line)
            if m:
                snippet = line[:100]
                status.update(f"[cyan]Building image[/] [dim]{snippet}[/]")
                continue

            lowered = line.lower()
            if "error" in lowered and "--no-" not in lowered:
                console.print(f"  [yellow]{line[:120]}[/]")
            status.update(
                f"[cyan]Building image[/] "
                f"[dim]{(last_step + ' · ') if last_step else ''}{line[:72]}[/]"
            )

    rc = proc.wait()
    return rc, last_line, output_lines


def _looks_like_stale_cache(output_lines: list[str]) -> bool:
    """Return True if the build failure looks like it was caused by
    stale layer-cache (e.g. old lockfiles, wrong Python version)."""
    blob = "\n".join(output_lines).lower()
    patterns = [
        "no interpreter found for python",
        "no matching distribution found",
        "package not found",
        "could not find a version that satisfies",
    ]
    return any(p in blob for p in patterns)


def _build_one(dockerfile: Path, tag: str) -> None:
    """Run a single ``docker build`` with the shared spinner and stale-cache
    retry. Exits the process on failure."""
    cmd = [ENGINE, "build", "-f", str(dockerfile), "-t", tag, str(DOCKER_CONTEXT_ROOT)]
    rc, last_line, output_lines = _run_build(cmd)

    if rc != 0 and _looks_like_stale_cache(output_lines):
        console.print()
        console.print(
            "[yellow]Build failed — looks like a stale layer cache "
            "(e.g. updated lockfiles not picked up).[/]"
        )
        console.print(
            "[yellow]Retrying with [bold]--no-cache[/] "
            "(full rebuild, may take a few minutes)…[/]"
        )
        console.print()
        cmd_nc = [
            ENGINE,
            "build",
            "--no-cache",
            "-f",
            str(dockerfile),
            "-t",
            tag,
            str(DOCKER_CONTEXT_ROOT),
        ]
        rc, last_line, output_lines = _run_build(cmd_nc)

    if rc != 0:
        console.print(f"[red bold]Build failed[/] (exit {rc}) for [bold]{tag}[/]")
        if last_line:
            console.print(f"  Last output: [dim]{last_line}[/]")
        sys.exit(rc)


def docker_build(harness: str = DEFAULT_HARNESS) -> None:
    """Build the base + harness images with a live progress spinner.

    The first build pulls the Python base, Chromium, ffmpeg, noVNC, and the
    selected harness dependencies; subsequent rebuilds are near-instant when
    the layer cache is warm. We show a banner only for the cold path.

    If a build fails with a pattern that suggests stale layer-cache
    (e.g. a lockfile mismatch), we automatically retry once with
    ``--no-cache`` so the user doesn't have to debug it manually.
    """
    if harness not in _HARNESS_DOCKERFILES:
        raise ValueError(
            f"Unknown harness {harness!r}; expected one of {list(_HARNESS_DOCKERFILES)}"
        )
    target_image = harness_image(harness)
    first_build = not _image_exists(target_image)

    if first_build:
        console.print()
        console.print(
            Panel(
                "[bold]First-time container build.[/]\n"
                f"This downloads Chromium, ffmpeg, noVNC, and {harness} dependencies\n"
                "and typically takes [bold]5–10 minutes[/] on a decent connection.\n"
                "[dim]Subsequent runs reuse the layer cache and finish in seconds.[/]",
                title=f"[bold]Building {target_image} image[/]",
                border_style="cyan",
            )
        )

    _build_one(BASE_DOCKERFILE, BASE_IMAGE)
    _build_one(_HARNESS_DOCKERFILES[harness], target_image)
    console.print(f"[green]✓[/] Container image ready ({target_image})")


def _fix_data_ownership(data_dir: Path) -> None:
    """On Linux + rootful Docker, files written inside the container are
    owned by root on the host. After ``docker cp``, the caller cannot
    ``rm -rf test-output/`` without sudo. Detect this and chown the tree
    back to the caller's UID/GID via a throwaway container (which has the
    root privileges needed to chown anything on the bind-mounted dir).

    No-op on macOS, on rootless podman, and when the tree is already
    owned by the caller.
    """
    if sys.platform != "linux":
        return
    if ENGINE != "docker":
        return
    if not data_dir.exists():
        return
    try:
        uid = os.getuid()
    except AttributeError:
        return
    try:
        needs_fix = any(
            p.stat().st_uid != uid for p in data_dir.rglob("*") if not p.is_symlink()
        )
    except OSError:
        needs_fix = True
    if not needs_fix:
        return

    print(f"  Fixing ownership of {data_dir} (rootful Docker -> host UID)")
    subprocess.run(
        [
            ENGINE,
            "run",
            "--rm",
            "-v",
            f"{data_dir.resolve()}:/fix",
            BASE_IMAGE,
            "chown",
            "-R",
            f"{uid}:{os.getgid()}",
            "/fix",
        ],
        check=False,
        capture_output=True,
    )


def _network_flags() -> list[str]:
    """Force slirp4netns on podman to avoid host-network port collisions."""
    if ENGINE == "podman":
        return ["--network=slirp4netns"]
    return []


def _proxy_env_flags() -> list[str]:
    """Forward host proxy env vars into the container.

    Inside the container 127.0.0.1 is its own loopback, not the host.
    Rewrite localhost references to the host gateway so the proxy is reachable.
    Both podman (host.containers.internal) and Docker Desktop
    (host.docker.internal) resolve to the Mac host.
    """
    host_gw = (
        "host.containers.internal" if ENGINE == "podman" else "host.docker.internal"
    )
    flags: list[str] = []
    has_proxy = False
    for var in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
        "NO_PROXY",
        "no_proxy",
    ):
        val = os.environ.get(var, "")
        if not val:
            continue
        if var not in ("NO_PROXY", "no_proxy"):
            has_proxy = True
        # Rewrite 127.0.0.1 / localhost to host gateway
        val = val.replace("127.0.0.1", host_gw).replace("localhost", host_gw)
        flags += ["-e", f"{var}={val}"]
    # Ensure container-internal traffic bypasses the proxy
    if has_proxy and not os.environ.get("NO_PROXY") and not os.environ.get("no_proxy"):
        flags += ["-e", "NO_PROXY=localhost,127.0.0.1"]
        flags += ["-e", "no_proxy=localhost,127.0.0.1"]
    return flags


def docker_run_human(
    name: str,
    instruction: str,
    schema_path: Path,
    personal_info_dir: Path,
    time_limit_s: int = 1800,
    host_port: int = 6080,
) -> None:
    # Human mode has no agent harness — base image carries everything
    # needed (Xvfb, Chrome, extension-server, noVNC).
    cmd = [
        ENGINE,
        "run",
        "-d",
        "--name",
        name,
        *_network_flags(),
        *_proxy_env_flags(),
        "-e",
        "HUMAN_MODE=1",
        "-e",
        f"INSTRUCTION={instruction}",
        "-e",
        f"TIME_LIMIT_S={time_limit_s}",
        "-p",
        f"{host_port}:6080",
        "-v",
        f"{schema_path.resolve()}:/eval-schema.json:ro",
        "-v",
        f"{personal_info_dir.resolve()}:/my-info:ro",
        BASE_IMAGE,
    ]
    run(cmd)


def docker_run(
    name: str,
    instruction: str,
    schema_path: Path,
    personal_info_dir: Path,
    model_cfg: dict,
    time_limit_s: int = 1800,
    host_port: int | None = None,
    harness: str = DEFAULT_HARNESS,
) -> None:
    env_flags = [
        ENGINE,
        "run",
        "-d",
        "--name",
        name,
        *_network_flags(),
        *_proxy_env_flags(),
        "-e",
        f"MODEL_NAME={model_cfg['model']}",
        "-e",
        f"BASE_URL={model_cfg['base_url']}",
        "-e",
        f"API_TYPE={model_cfg['api_type']}",
        "-e",
        f"API_KEYS={json.dumps(model_cfg.get('api_keys', []))}",
        "-e",
        f"API_KEY={model_cfg.get('api_key', '')}",
        "-e",
        f"INSTRUCTION={instruction}",
        "-e",
        f"TIME_LIMIT_S={time_limit_s}",
        "-v",
        f"{schema_path.resolve()}:/eval-schema.json:ro",
        "-v",
        f"{personal_info_dir.resolve()}:/my-info:ro",
    ]
    # Expose noVNC so the user can watch the agent in real-time.
    if host_port is not None:
        env_flags += ["-p", f"{host_port}:6080"]
    # host.docker.internal needs explicit mapping on Linux (not Docker Desktop)
    if "host.docker.internal" in model_cfg["base_url"]:
        env_flags += ["--add-host=host.docker.internal:host-gateway"]
    if model_cfg.get("thinking_level"):
        env_flags += ["-e", f"THINKING_LEVEL={model_cfg['thinking_level']}"]
    if model_cfg.get("temperature") is not None:
        env_flags += ["-e", f"TEMPERATURE={model_cfg['temperature']}"]
    if model_cfg.get("max_tokens") is not None:
        env_flags += ["-e", f"MAX_TOKENS={model_cfg['max_tokens']}"]
    run([*env_flags, harness_image(harness)])


def docker_wait(name: str) -> None:
    """Block until the container exits, showing a live status line."""
    start = time.time()
    # Launch `docker wait` in background so we can poll status
    proc = subprocess.Popen(
        [ENGINE, "wait", name], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    last_actions = 0
    with Status("[dim]starting...[/]", console=console) as status:
        while proc.poll() is None:
            elapsed = int(time.time() - start)
            mins, secs = divmod(elapsed, 60)
            # Query actions count from container. Under high concurrency
            # podman exec can take several seconds; we keep the timeout low
            # to stay responsive but swallow the exception so a slow exec
            # never kills the whole job.
            try:
                r = subprocess.run(
                    [ENGINE, "exec", name, "wc", "-l", "/data/actions.jsonl"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if r.returncode == 0:
                    try:
                        last_actions = int(r.stdout.strip().split()[0])
                    except (ValueError, IndexError):
                        pass
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass
            status.update(f"[dim]{mins:02d}:{secs:02d}  •  {last_actions} actions[/]")
            # Poll every 5s
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    elapsed = int(time.time() - start)
    mins, secs = divmod(elapsed, 60)
    console.print(f"  Container exited ({mins}m{secs:02d}s, {last_actions} actions)")


def docker_copy(name: str, output_dir: Path) -> None:
    run([ENGINE, "cp", f"{name}:/data", str(output_dir / "data")])
    # Remove internal marker file. Keep harness *.log diagnostics for now
    # — useful when agent_exited with api_call_count=0 needs root cause.
    (output_dir / "data" / ".stop-requested").unlink(missing_ok=True)


def docker_logs(name: str) -> None:
    subprocess.run([ENGINE, "logs", "--tail", "40", name])


def docker_rm(name: str) -> None:
    subprocess.run([ENGINE, "rm", "-f", name], capture_output=True)


# -- Results --


def validate_task_data(task: Any, task_file: Path) -> dict:
    if not isinstance(task, dict):
        raise ValueError(f"{task_file} must contain a JSON object")
    instruction = task.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("task instruction must be a non-empty string")
    eval_schema = task.get("eval_schema")
    if not isinstance(eval_schema, dict):
        raise ValueError("task eval_schema must be an object")
    if not isinstance(eval_schema.get("url_pattern"), str):
        raise ValueError("task eval_schema.url_pattern must be a string")
    if not isinstance(eval_schema.get("method"), str):
        raise ValueError("task eval_schema.method must be a string")
    try:
        time_limit = float(task.get("time_limit"))
    except (TypeError, ValueError):
        raise ValueError("task time_limit must be a number") from None
    if time_limit <= 0:
        raise ValueError("task time_limit must be greater than 0")
    return task


def _count_jsonl(path: Path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    try:
        with path.open(errors="replace") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _line_has_api_or_credit_evidence(line: str) -> bool:
    lowered = f" {line.lower()} "
    return any(pattern in lowered for pattern in API_OR_CREDIT_PATTERNS)


def collect_run_metrics(output_dir: Path) -> dict[str, Any]:
    data_dir = output_dir / "data"
    actions_file = data_dir / "actions.jsonl"
    requests_file = data_dir / "requests.jsonl"
    messages_file = data_dir / "agent-messages.jsonl"
    screenshots_dir = data_dir / "screenshots"
    recording_file = data_dir / "recording.mp4"
    interception_file = data_dir / "interception.json"

    metrics: dict[str, Any] = {
        "actions": _count_jsonl(actions_file),
        "requests": _count_jsonl(requests_file),
        "messages": _count_jsonl(messages_file),
        "screenshots": (
            sum(1 for _ in screenshots_dir.iterdir()) if screenshots_dir.is_dir() else 0
        ),
        "recording_bytes": (
            recording_file.stat().st_size if recording_file.exists() else 0
        ),
        "api_calls": 0,
        "stop_reason": None,
        "missing_files": [],
        "api_or_credit_evidence": None,
    }

    for rel in (
        "data/actions.jsonl",
        "data/requests.jsonl",
        "data/agent-messages.jsonl",
        "data/interception.json",
        "data/recording.mp4",
    ):
        if not (output_dir / rel).exists():
            metrics["missing_files"].append(rel)

    interception = _read_json(interception_file)
    if isinstance(interception, dict):
        metrics["stop_reason"] = interception.get("stop_reason")

    explicit_api_calls: int | None = None
    derived_api_call_keys: set[str] = set()
    derived_api_start_keys: set[tuple[str, str, str]] = set()
    derived_api_response_start_keys: set[tuple[str, str, str]] = set()
    if messages_file.exists():
        try:
            with messages_file.open(errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if event.get("type") == "session_meta" and isinstance(
                        event.get("api_call_count"), int
                    ):
                        explicit_api_calls = event["api_call_count"]
                    msg = event.get("message")
                    if isinstance(msg, dict):
                        role = msg.get("role")
                        if role == "assistant" and (
                            msg.get("api") or msg.get("provider") or msg.get("usage")
                        ):
                            provider = str(msg.get("provider") or "")
                            model = str(msg.get("model") or "")
                            timestamp = str(msg.get("timestamp") or "")
                            response_id = msg.get("responseId")
                            if response_id:
                                key = "|".join(
                                    [
                                        provider,
                                        model,
                                        str(response_id),
                                    ]
                                )
                                if timestamp:
                                    derived_api_response_start_keys.add(
                                        (provider, model, timestamp)
                                    )
                            elif (
                                event.get("type") == "message_start"
                                and not msg.get("content")
                                and timestamp
                            ):
                                key = ""
                                derived_api_start_keys.add((provider, model, timestamp))
                            else:
                                key = "|".join(
                                    [
                                        provider,
                                        model,
                                        timestamp,
                                        str(event.get("id") or ""),
                                    ]
                                )
                            if key:
                                derived_api_call_keys.add(key)
                        err = msg.get("errorMessage") or msg.get("error")
                        if (
                            err
                            and metrics["api_or_credit_evidence"] is None
                            and _line_has_api_or_credit_evidence(str(err))
                        ):
                            metrics["api_or_credit_evidence"] = str(err)[:500]
        except OSError:
            pass

    if explicit_api_calls is not None:
        metrics["api_calls"] = explicit_api_calls
    elif derived_api_call_keys or derived_api_start_keys:
        for key in derived_api_start_keys - derived_api_response_start_keys:
            derived_api_call_keys.add("message_start|" + "|".join(key))
        metrics["api_calls"] = len(derived_api_call_keys)

    if metrics["api_or_credit_evidence"] is None and data_dir.exists():
        for log_file in data_dir.glob("*.log"):
            try:
                with log_file.open(errors="replace") as f:
                    for line in f:
                        if _line_has_api_or_credit_evidence(line):
                            metrics["api_or_credit_evidence"] = (
                                f"{log_file.name}: {line.strip()[:450]}"
                            )
                            break
            except OSError:
                continue
            if metrics["api_or_credit_evidence"] is not None:
                break

    return metrics


def classify_run(
    output_dir: Path,
    intercepted: bool,
    default_failure_category: str | None = None,
) -> dict[str, Any]:
    metrics = collect_run_metrics(output_dir)
    infra_flags: list[str] = []
    if metrics["api_calls"] == 0:
        infra_flags.append("zero_api_calls")
    if metrics["actions"] == 0:
        infra_flags.append("zero_actions")
    if metrics["requests"] == 0:
        infra_flags.append("zero_requests")
    if metrics["messages"] == 0:
        infra_flags.append("zero_agent_messages")
    if metrics["recording_bytes"] == 0:
        infra_flags.append("missing_or_empty_recording")
    for rel in metrics["missing_files"]:
        infra_flags.append(f"missing:{rel}")

    if intercepted:
        category = None
        result_category = "intercepted"
    elif default_failure_category:
        category = default_failure_category
        result_category = default_failure_category
    elif metrics["api_or_credit_evidence"]:
        category = "api_or_credit"
        result_category = category
    elif metrics["stop_reason"] in INFRA_STOP_REASONS:
        category = "infra_failure"
        result_category = category
    elif (
        metrics["api_calls"] == 0
        and metrics["actions"] == 0
        and metrics["requests"] == 0
    ):
        category = "infra_failure"
        result_category = category
    elif metrics["messages"] == 0 or not (output_dir / "data").exists():
        category = "infra_failure"
        result_category = category
    else:
        category = "model_not_intercepted"
        result_category = category

    adjusted_eligible = category not in NON_MODEL_FAILURE_CATEGORIES
    return {
        "result_category": result_category,
        "failure_category": category,
        "infra_failure": category == "infra_failure",
        "adjusted_eligible": adjusted_eligible,
        "infra_flags": infra_flags,
        "metrics": metrics,
    }


def make_run_meta(
    *,
    task: dict | None,
    task_json_sha256: str | None,
    case_name: str,
    args: argparse.Namespace,
    model_cfg: dict | None,
    email: str | None,
    ts: str,
    duration: float,
    intercepted: bool,
    classification: dict[str, Any],
    failure_reason: str | None = None,
    extra_info_warnings: list[str] | None = None,
) -> dict[str, Any]:
    task = task if isinstance(task, dict) else {}
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    if args.human:
        model = "human"
        harness = "human"
        thinking_level = temperature = max_tokens = None
    else:
        model = model_cfg["model"] if model_cfg else args.model
        harness = args.harness
        thinking_level = model_cfg.get("thinking_level") if model_cfg else None
        temperature = model_cfg.get("temperature") if model_cfg else None
        max_tokens = model_cfg.get("max_tokens") if model_cfg else None

    meta = {
        "test_case": case_name,
        **metadata,
        "task_json_sha256": task_json_sha256,
        "instruction": task.get("instruction"),
        "model": model,
        "harness": harness,
        "thinking_level": thinking_level,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "email_used": email,
        "timestamp": ts,
        "time_limit_minutes": task.get("time_limit"),
        "duration_seconds": round(duration),
        "intercepted": intercepted,
        "result_category": classification["result_category"],
        "failure_category": classification["failure_category"],
        "infra_failure": classification["infra_failure"],
        "adjusted_eligible": classification["adjusted_eligible"],
        "infra_flags": classification["infra_flags"],
        "run_metrics": classification["metrics"],
    }
    if failure_reason:
        meta["failure_reason"] = failure_reason
    if extra_info_warnings:
        meta["extra_info_warnings"] = extra_info_warnings
    return meta


def write_run_meta(output_dir: Path, meta: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run-meta.json").write_text(json.dumps(meta, indent=2))


def ensure_interception(output_dir: Path):
    """If the interceptor didn't produce interception.json, create one with the stop reason."""
    stop_reason_file = output_dir / "data" / ".stop-reason"
    reason = (
        stop_reason_file.read_text().strip() if stop_reason_file.exists() else "unknown"
    )
    stop_reason_file.unlink(missing_ok=True)
    interception_file = output_dir / "data" / "interception.json"
    if interception_file.exists():
        return
    descriptions = {
        "time_limit_exceeded": "Session stopped: time limit exceeded before the interceptor was triggered.",
        "agent_idle": "Session stopped: agent went idle (300s no actions) before triggering the interceptor.",
        "agent_exited": "Session stopped: agent process exited before triggering the interceptor.",
        "vnc_disconnected": "Session stopped: human disconnected from VNC without triggering the interceptor.",
        "chrome_cdp_timeout": "Session stopped: Chrome CDP was not ready after 30s (browser failed to start).",
        "gateway_failed": "Session stopped: OpenClaw gateway died on startup.",
        "opencode_failed": "Session stopped: opencode process died on startup.",
        "claude_code_failed": "Session stopped: Claude Code process died on startup.",
        "codex_failed": "Session stopped: Codex CLI process died on startup.",
        "browser_use_failed": "Session stopped: browser-use process died on startup.",
        "hermes_failed": "Session stopped: Hermes Agent process died on startup.",
        "pi_failed": "Session stopped: Pi coding agent process died on startup.",
        "proxy_failed": "Session stopped: LiteLLM API translation proxy failed to start.",
        "missing_harness": "Session stopped: container image was built without a harness layer.",
    }
    description = descriptions.get(reason, f"Session stopped: {reason}.")
    schema_file = output_dir / "eval-schema.json"
    schema = json.loads(schema_file.read_text()) if schema_file.exists() else None
    result = {
        "intercepted": False,
        "stop_reason": reason,
        "stop_description": description,
        "request": None,
        "schema": schema,
    }
    interception_file.parent.mkdir(parents=True, exist_ok=True)
    interception_file.write_text(json.dumps(result, indent=2))


def print_results(output_dir: Path) -> bool:
    data_dir = output_dir / "data"

    # Actions
    actions_file = data_dir / "actions.jsonl"
    if actions_file.exists():
        actions = [
            json.loads(line)
            for line in actions_file.read_text().splitlines()
            if line.strip()
        ]
        print(f"Actions recorded: {len(actions)}")
        for a in actions:
            print(f"  {a['type']:10s}  {a.get('url', '')[:70]}")
    else:
        print("No actions.jsonl found")

    # HTTP Requests
    requests_file = data_dir / "requests.jsonl"
    if requests_file.exists():
        request_lines = [
            line for line in requests_file.read_text().splitlines() if line.strip()
        ]
        print(f"HTTP requests logged: {len(request_lines)}")

    # Interception
    interception_file = data_dir / "interception.json"
    result = json.loads(interception_file.read_text())
    intercepted = result.get("intercepted", False)
    print(f"Intercepted: {intercepted}")
    if result.get("stop_reason"):
        print(f"Stop reason: {result['stop_reason']}")
    if result.get("request"):
        print(f"Request URL: {result['request']['url']}")
        print(f"Request method: {result['request']['method']}")
        if result["request"].get("body"):
            print(f"Body: {json.dumps(result['request']['body'])[:300]}")
    return intercepted


def main():
    ensure_workspace_templates()

    parser = argparse.ArgumentParser(description="Run a single ClawBench test case")
    parser.add_argument(
        "test_case_dir", type=Path, help="Path to the test case directory"
    )
    parser.add_argument(
        "model",
        type=str,
        nargs="?",
        default=None,
        help="Model name (key in models/models.yaml, required for agent mode)",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="Human mode: expose Chrome via noVNC instead of running an agent",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        type=Path,
        default=None,
        help="Directory to write output data to (default: <project>/test-output)",
    )
    parser.add_argument(
        "--no-build",
        dest="no_build",
        action="store_true",
        help="Skip building the container image (assumes it already exists)",
    )
    parser.add_argument(
        "--no-upload",
        dest="no_upload",
        action="store_true",
        help="Skip HuggingFace upload even if HF_TOKEN is configured",
    )
    parser.add_argument(
        "--harness",
        choices=HARNESSES,
        default=DEFAULT_HARNESS,
        help=f"Coding-agent harness (default: {DEFAULT_HARNESS})",
    )
    parser.add_argument(
        "--judge",
        default="deepseek-v4-pro",
        help=(
            "Model name (key in models/models.yaml) used as LLM judge over the "
            "intercepted HTTP request. Pass = intercepted AND judge says match. "
            "Default: deepseek-v4-pro. Use --no-judge to disable."
        ),
    )
    parser.add_argument(
        "--no-judge",
        dest="no_judge",
        action="store_true",
        help="Skip the LLM judge stage; pass = intercepted (stage 1 only)",
    )
    args = parser.parse_args()

    if not args.human and args.model is None:
        parser.error("model is required for agent mode (or use --human)")

    # Load infrastructure config from .env (PurelyMail only)
    env = load_runtime_env()
    infra_required = ["PURELY_MAIL_API_KEY", "PURELY_MAIL_DOMAIN"]
    missing = [k for k in infra_required if not env.get(k)]
    if missing:
        for k in missing:
            print(f"ERROR: {k} not set in .env")
        sys.exit(1)
    pm_key: str = env["PURELY_MAIL_API_KEY"]
    pm_domain: str = env["PURELY_MAIL_DOMAIN"]

    # HuggingFace upload (optional)
    hf_env = {
        "HF_TOKEN": env.get("HF_TOKEN", ""),
        "HF_REPO_ID": env.get("HF_REPO_ID", ""),
    }
    do_upload = hf_upload_enabled(hf_env) and not args.no_upload

    start_time = time.time()
    task_dir = resolve_test_case_dir(args.test_case_dir)
    case_name = task_dir.name
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    model_cfg: dict | None = None
    if args.human:
        safe_model = "human"
        harness_tag = "human"
    else:
        model_cfg = load_model_config(args.model)
        safe_model = re.sub(r"[/:]+", "--", args.model)
        harness_tag = args.harness

    container = f"clawbench-{harness_tag}-{case_name}-{safe_model}-{int(time.time())}"
    run_dir_name = f"{harness_tag}-{case_name}-{safe_model}-{ts}"

    if args.output_dir is not None:
        output_dir = args.output_dir.resolve() / safe_model / run_dir_name
    else:
        output_dir = WORKSPACE_ROOT / "test-output" / safe_model / run_dir_name
    output_dir.mkdir(parents=True, exist_ok=True)

    task: dict | None = None
    task_json_sha256: str | None = None
    time_limit_s = 1800
    extra_info_warnings: list[str] = []
    intercepted = False

    # Load and validate task after output_dir exists so task-data failures
    # still leave a run-meta.json for batch/report classification.
    task_file = task_dir / "task.json"
    try:
        if not task_file.exists():
            raise FileNotFoundError(f"{task_file} not found")
        task_bytes = task_file.read_bytes()
        loaded_task = json.loads(task_bytes)
        task = validate_task_data(loaded_task, task_file)
        task_json_sha256 = hashlib.sha256(task_bytes).hexdigest()
        time_limit_s = int(float(task["time_limit"]) * 60)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        duration = time.time() - start_time
        classification = classify_run(output_dir, False, "task_data")
        meta = make_run_meta(
            task=task,
            task_json_sha256=task_json_sha256,
            case_name=case_name,
            args=args,
            model_cfg=model_cfg,
            email=None,
            ts=ts,
            duration=duration,
            intercepted=False,
            classification=classification,
            failure_reason=f"task_data: {e}",
        )
        write_run_meta(output_dir, meta)
        print(f"ERROR: task_data: {e}")
        sys.exit(2)

    if not args.no_build:
        step("Building container image")
        try:
            docker_build(args.harness)
        except SystemExit as e:
            duration = time.time() - start_time
            classification = classify_run(output_dir, False, "infra_failure")
            meta = make_run_meta(
                task=task,
                task_json_sha256=task_json_sha256,
                case_name=case_name,
                args=args,
                model_cfg=model_cfg,
                email=None,
                ts=ts,
                duration=duration,
                intercepted=False,
                classification=classification,
                failure_reason=f"infra_failure: container build exited {e.code}",
            )
            write_run_meta(output_dir, meta)
            raise

    email = None
    personal_info_tmp: Path | None = None
    phase = "startup"
    try:
        assert task is not None

        phase = "creating_email"
        step("Creating disposable email")
        email, email_pw = create_email(pm_key, pm_domain)

        phase = "preparing_personal_info"
        step("Preparing personal info")
        personal_info_tmp = prepare_personal_info(
            SHARED_ROOT, email, email_pw, output_dir
        )
        extra_info_warnings = copy_extra_info(task, task_dir, personal_info_tmp)
        print(f"  Personal info dir: {personal_info_tmp}")

        # Write eval schema for the interceptor
        phase = "writing_eval_schema"
        schema_path = output_dir / "eval-schema.json"
        schema_path.write_text(json.dumps(task["eval_schema"], indent=2))

        phase = "building_instruction"
        step("Building instruction")
        instruction = build_instruction(task)
        print(instruction[:500])

        if args.human:
            phase = "starting_container"
            step("Starting container (human mode)")
            # Avoid hard-coded 6080:6080 collisions under concurrent runs.
            host_port = _pick_free_port(6080)
            docker_run_human(
                container,
                instruction,
                schema_path,
                personal_info_tmp,
                time_limit_s,
                host_port=host_port,
            )

            # Graceful stop on Ctrl+C: give container time to flush recording
            def handle_sigint(sig, frame):
                print("\nCtrl+C received, stopping container gracefully...")
                subprocess.run(
                    [ENGINE, "stop", "-t", "20", container], capture_output=True
                )

            signal.signal(signal.SIGINT, handle_sigint)

            vnc_url = f"http://localhost:{host_port}/vnc.html"
            console.print(f"\n  noVNC: [link={vnc_url}]{vnc_url}[/link]")
            if host_port != 6080:
                console.print(
                    f"  [dim](port 6080 was busy, auto-picked {host_port})[/dim]"
                )
            console.print(f"  Task:  {task['instruction'][:200]}")
            console.print(f"  Email: {email}  Password: {email_pw}")
            console.print(f"  Time limit: {task['time_limit']} minutes")
            console.print("  Close the noVNC tab when done.\n")

            step(f"Waiting for human (max {task['time_limit']}min)")
        else:
            phase = "starting_container"
            step("Starting container")
            assert model_cfg is not None
            host_port = _pick_free_port(6080)
            docker_run(
                container,
                instruction,
                schema_path,
                personal_info_tmp,
                model_cfg,
                time_limit_s=time_limit_s,
                host_port=host_port,
                harness=args.harness,
            )

            vnc_url = f"http://localhost:{host_port}/vnc.html"
            console.print(f"\n  noVNC: [link={vnc_url}]{vnc_url}[/link]")
            if host_port != 6080:
                console.print(
                    f"  [dim](port 6080 was busy, auto-picked {host_port})[/dim]"
                )
            console.print("  Open the URL above to watch the agent in real-time.\n")

            step(f"Agent running (max {task['time_limit']}min)")

        phase = "waiting_for_container"
        docker_wait(container)

        phase = "container_logs"
        step("Container logs")
        docker_logs(container)

        phase = "copying_results"
        step("Copying results")
        docker_copy(container, output_dir)
        _fix_data_ownership(output_dir / "data")

        phase = "ensuring_interception"
        ensure_interception(output_dir)

        phase = "printing_results"
        step("Results")
        intercepted = print_results(output_dir)

        # Stage 2 — LLM judge (default on, --no-judge to skip).
        # Only invoked when stage 1 (intercepted) succeeded; otherwise the
        # task already fails at stage 1 and there's nothing to judge.
        judge_result: dict[str, Any] | None = None
        if intercepted and not args.no_judge and args.judge:
            phase = "running_judge"
            step("LLM judge")
            try:
                from clawbench.runner.judge import judge_request

                judge_cfg = load_model_config(args.judge)
                instruction_text = (
                    task.get("instruction") if isinstance(task, dict) else ""
                ) or ""
                interception_path = output_dir / "data" / "interception.json"
                if interception_path.exists():
                    intercept_blob = json.loads(interception_path.read_text())
                else:
                    intercept_blob = {}
                judge_result = judge_request(
                    judge_cfg,
                    judge_cfg.get("model", args.judge),
                    instruction_text,
                    intercept_blob,
                )
                (output_dir / "judge.json").write_text(
                    json.dumps(judge_result, indent=2, ensure_ascii=False)
                )
                print(
                    f"Judge ({args.judge}): "
                    f"match={judge_result.get('match')}  "
                    f"reason={judge_result.get('reason', '')[:160]}"
                )
            except Exception as e:
                judge_result = {
                    "match": None,
                    "reason": f"judge_setup_failed: {e}",
                    "judge_model": args.judge,
                    "raw": None,
                    "error": str(e),
                }
                (output_dir / "judge.json").write_text(
                    json.dumps(judge_result, indent=2, ensure_ascii=False)
                )
                print(f"Judge skipped due to error: {e}")

        # Write run metadata
        phase = "writing_run_meta"
        duration = time.time() - start_time
        classification = classify_run(output_dir, intercepted)
        meta = make_run_meta(
            task=task,
            task_json_sha256=task_json_sha256,
            case_name=case_name,
            args=args,
            model_cfg=model_cfg,
            email=email,
            ts=ts,
            duration=duration,
            intercepted=intercepted,
            classification=classification,
            extra_info_warnings=extra_info_warnings,
        )
        if judge_result is not None:
            meta["judge"] = judge_result
            meta["judge_match"] = judge_result.get("match")
        meta["pass"] = bool(
            intercepted
            and (
                args.no_judge
                or judge_result is None
                or judge_result.get("match") is True
            )
        )
        write_run_meta(output_dir, meta)

        if do_upload:
            phase = "uploading"
            step("Uploading to HuggingFace")
            repo_path = f"{safe_model}/{run_dir_name}"
            upload_run(output_dir, repo_path, hf_env)

    except Exception as e:
        category = "infra_failure"
        if phase == "building_instruction":
            category = "build_instruction"
        elif phase == "writing_eval_schema":
            category = "task_data"
        try:
            if (output_dir / "data").exists():
                ensure_interception(output_dir)
        except Exception:
            pass
        duration = time.time() - start_time
        classification = classify_run(output_dir, False, category)
        meta = make_run_meta(
            task=task,
            task_json_sha256=task_json_sha256,
            case_name=case_name,
            args=args,
            model_cfg=model_cfg,
            email=email,
            ts=ts,
            duration=duration,
            intercepted=False,
            classification=classification,
            failure_reason=f"{category}: {phase}: {type(e).__name__}: {e}",
            extra_info_warnings=extra_info_warnings,
        )
        write_run_meta(output_dir, meta)
        print(f"ERROR: {phase} failed: {e}")
        sys.exit(2)
    finally:
        step("Cleanup")
        docker_rm(container)
        if email:
            delete_email(pm_key, email)
        if personal_info_tmp and personal_info_tmp.exists():
            shutil.rmtree(personal_info_tmp, ignore_errors=True)
        (output_dir / "eval-schema.json").unlink(missing_ok=True)

    # Final pass status: stage 1 (intercepted) AND stage 2 (judge match), unless --no-judge.
    final_pass = bool(meta.get("pass"))
    if not intercepted:
        print(f"\nNOT INTERCEPTED — results in {output_dir}")
        sys.exit(1)
    if (
        not args.no_judge
        and judge_result is not None
        and judge_result.get("match") is not True
    ):
        verdict = judge_result.get("match")
        reason = judge_result.get("reason", "")
        print(
            f"\nINTERCEPTED but JUDGE {'MISMATCH' if verdict is False else 'INCONCLUSIVE'} "
            f"— results in {output_dir}\n  reason: {reason[:200]}"
        )
        sys.exit(1)
    if final_pass:
        print(f"\nINTERCEPTED + JUDGE MATCH — results in {output_dir}")
    else:
        print(f"\nINTERCEPTED — results in {output_dir}")


if __name__ == "__main__":
    main()
