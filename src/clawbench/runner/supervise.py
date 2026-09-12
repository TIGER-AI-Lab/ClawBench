"""Re-invoke an aborted batch until it finishes — `clawbench-batch --auto-restart`.

A multi-hour batch dies for reasons that have nothing to do with the agent:
Chromium balloons and the kernel OOM-kills the container, a provider returns
502 for thirty seconds, the queue cap trips at task 75. The batch process is
gone, so nothing inside it can retry. This runs *outside* it: a small
supervisor that spawns `clawbench-batch` as a child, and when the child exits
non-zero waits and spawns it again with `--resume` pointing at the same batch
directory, up to a bounded number of times.

The supervisor owns nothing heavy — no browser, no containers, no model
calls — which is exactly why it survives the failures the batch does not.
"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_RESTART_DELAY_S = 30.0
BATCH_MODULE = "clawbench.runner.batch"

# Exit status for "the operator interrupted us", mirroring the shell's 128+SIGINT.
INTERRUPTED = 130

Spawn = Callable[[list[str]], int]
Sleep = Callable[[float], None]


def _default_spawn(cmd: list[str]) -> int:
    """Run the batch as a child and return its exit status.

    A KeyboardInterrupt here means the operator hit Ctrl-C: the child shares
    our process group and received it too, so wait for it to wind down rather
    than orphaning its containers, then re-raise so the loop stops.
    """
    proc = subprocess.Popen(cmd)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.terminate()
        raise


def strip_supervisor_flags(argv: list[str]) -> list[str]:
    """Remove the flags the supervisor consumes so the child does not recurse."""
    out: list[str] = []
    skip_next = False
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg in ("--auto-restart", "--auto-restart-delay", "--resume"):
            skip_next = True
            continue
        if arg.startswith(("--auto-restart=", "--auto-restart-delay=", "--resume=")):
            continue
        out.append(arg)
    return out


def resolve_batch_dir(resume: str | None, output_dir: str | Path) -> Path:
    """The one batch directory every attempt resumes into.

    `--resume` carries over an existing batch; otherwise a fresh batch
    directory is created here so that the *first* attempt already runs under
    `--resume` and every later attempt lands in the same place.
    """
    if resume:
        return Path(resume).resolve()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    batch_dir = Path(output_dir).resolve() / f"batch-{ts}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    return batch_dir


def run_supervised(
    child_argv: list[str],
    *,
    batch_dir: Path,
    max_restarts: int,
    delay_s: float = DEFAULT_RESTART_DELAY_S,
    spawn: Spawn = _default_spawn,
    sleep: Sleep = time.sleep,
    log: Callable[[str], None] = print,
) -> int:
    """Run the batch, restarting on non-zero exit up to ``max_restarts`` times.

    Returns the final child's exit status: 0 only when an attempt finished
    with every job in a terminal state. A child that was interrupted by the
    operator is not restarted.
    """
    attempts = max_restarts + 1
    cmd = [
        sys.executable,
        "-m",
        BATCH_MODULE,
        *child_argv,
        "--resume",
        str(batch_dir),
    ]
    rc = 1
    for attempt in range(1, attempts + 1):
        log(
            f"[SUPERVISOR] attempt {attempt}/{attempts}: "
            f"clawbench-batch --resume {batch_dir}"
        )
        started = time.monotonic()
        try:
            rc = spawn(cmd)
        except KeyboardInterrupt:
            log("[SUPERVISOR] interrupted by operator; not restarting")
            return INTERRUPTED
        elapsed = time.monotonic() - started
        if rc == 0:
            log(f"[SUPERVISOR] batch finished cleanly on attempt {attempt}")
            return 0
        log(
            f"[SUPERVISOR] attempt {attempt} exited with status {rc} "
            f"after {elapsed / 60:.1f} min"
        )
        if attempt < attempts:
            log(f"[SUPERVISOR] restarting in {delay_s:.0f}s")
            sleep(delay_s)
    log(
        f"[SUPERVISOR] giving up after {attempts} attempt(s); "
        f"resume manually with: clawbench-batch --resume {batch_dir} ..."
    )
    return rc
