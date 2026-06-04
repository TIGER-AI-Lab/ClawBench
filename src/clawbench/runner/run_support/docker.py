"""Container build and runtime helpers for single runs."""

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.status import Status

from clawbench.runner.run_support.config import (
    BASE_IMAGE,
    DEFAULT_HARNESS,
    ENGINE,
    HARNESSES,
    IMAGE,
    harness_image,
)
from clawbench.utils.paths import DOCKER_CONTEXT_ROOT, HARNESS_ROOT

console = Console()

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
    "harbor": HARNESS_ROOT / "harbor" / "Dockerfile.harbor",
}


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


def image_exists(ref: str = IMAGE) -> bool:
    return (
        subprocess.run(
            [ENGINE, "image", "inspect", ref],
            capture_output=True,
        ).returncode
        == 0
    )


def image_id(ref: str) -> str | None:
    try:
        r = subprocess.run(
            [ENGINE, "image", "inspect", ref, "--format", "{{.Id}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    image_id_value = r.stdout.strip()
    return image_id_value or None


def container_engine_version() -> str | None:
    try:
        r = subprocess.run(
            [ENGINE, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def pick_free_port(preferred: int = 6080) -> int:
    """Return an OS-assigned ephemeral port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_STEP_RE = re.compile(r"^(?:STEP|Step)\s+(\d+)(?:/(\d+))?", re.IGNORECASE)
_BK_STEP_RE = re.compile(r"^#(\d+)\s+\[")


def _run_build(cmd: list[str]) -> tuple[int, str, list[str]]:
    """Execute a build command with a live spinner."""
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
    status_msg = "[cyan]Starting build...[/]"
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
                status.update(f"[cyan]Building image - {last_step}[/] [dim]{rest}[/]")
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
                f"[dim]{(last_step + ' - ') if last_step else ''}{line[:72]}[/]"
            )

    rc = proc.wait()
    return rc, last_line, output_lines


def _looks_like_stale_cache(output_lines: list[str]) -> bool:
    """Return True if the build failure looks like stale layer-cache."""
    blob = "\n".join(output_lines).lower()
    patterns = [
        "no interpreter found for python",
        "no matching distribution found",
        "package not found",
        "could not find a version that satisfies",
    ]
    return any(p in blob for p in patterns)


def _build_one(dockerfile: Path, tag: str) -> None:
    """Run one container build with a stale-cache retry."""
    cmd = [ENGINE, "build", "-f", str(dockerfile), "-t", tag, str(DOCKER_CONTEXT_ROOT)]
    rc, last_line, output_lines = _run_build(cmd)

    if rc != 0 and _looks_like_stale_cache(output_lines):
        console.print()
        console.print(
            "[yellow]Build failed - looks like a stale layer cache "
            "(e.g. updated lockfiles not picked up).[/]"
        )
        console.print(
            "[yellow]Retrying with [bold]--no-cache[/] "
            "(full rebuild, may take a few minutes)...[/]"
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
    """Build the base + harness images with a live progress spinner."""
    if harness not in _HARNESS_DOCKERFILES:
        raise ValueError(
            f"Unknown harness {harness!r}; expected one of {list(HARNESSES)}"
        )
    target_image = harness_image(harness)
    first_build = not image_exists(target_image)

    if first_build:
        console.print()
        console.print(
            Panel(
                "[bold]First-time container build.[/]\n"
                f"This downloads Chromium, ffmpeg, noVNC, and {harness} dependencies\n"
                "and typically takes [bold]5-10 minutes[/] on a decent connection.\n"
                "[dim]Subsequent runs reuse the layer cache and finish in seconds.[/]",
                title=f"[bold]Building {target_image} image[/]",
                border_style="cyan",
            )
        )

    _build_one(BASE_DOCKERFILE, BASE_IMAGE)
    _build_one(_HARNESS_DOCKERFILES[harness], target_image)
    console.print(f"[green]✓[/] Container image ready ({target_image})")


def fix_data_ownership(data_dir: Path) -> None:
    """Fix root-owned copied data on Linux + rootful Docker."""
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
    """Forward host proxy env vars into the container."""
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
        val = val.replace("127.0.0.1", host_gw).replace("localhost", host_gw)
        flags += ["-e", f"{var}={val}"]
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
    if host_port is not None:
        env_flags += ["-p", f"{host_port}:6080"]
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
    proc = subprocess.Popen(
        [ENGINE, "wait", name], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    last_actions = 0
    with Status("[dim]starting...[/]", console=console) as status:
        while proc.poll() is None:
            elapsed = int(time.time() - start)
            mins, secs = divmod(elapsed, 60)
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
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    elapsed = int(time.time() - start)
    mins, secs = divmod(elapsed, 60)
    console.print(f"  Container exited ({mins}m{secs:02d}s, {last_actions} actions)")


def docker_copy(name: str, output_dir: Path) -> None:
    run([ENGINE, "cp", f"{name}:/data", str(output_dir / "data")])
    (output_dir / "data" / ".stop-requested").unlink(missing_ok=True)


def docker_logs(name: str) -> None:
    subprocess.run([ENGINE, "logs", "--tail", "40", name])


def docker_rm(name: str) -> None:
    subprocess.run([ENGINE, "rm", "-f", name], capture_output=True)
