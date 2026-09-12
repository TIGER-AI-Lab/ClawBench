"""``clawbench-batch-watch`` — tell someone when a long batch aborts or finishes.

A V2 sweep runs 8–20 hours. When it dies at task 61 nobody finds out until
someone looks, and a partial cell sits on the leaderboard until then. This
polls a batch directory and posts to a webhook on abort, on completion, and
optionally every N completed tasks — so the operator learns within a minute,
not the next morning.

It reads only artifacts the batch already writes (``run-meta.json`` per run,
``batch-logs/*.log``, ``batch-summary.json`` at the end) and needs nothing
from the batch process itself. Liveness comes from ``--pid`` when given, else
from a stall timeout on artifact activity.

Routing is per operator: ``~/.config/clawbench/notify.toml``, overridden by
flags. Slack and Discord webhooks both accept the payload sent here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_INTERVAL_S = 60.0
# Longer than any single V2 task limit plus judge and teardown, so a quiet
# batch dir means the process is gone, not merely busy.
DEFAULT_STALL_TIMEOUT_S = 45 * 60
CONFIG_PATH = Path.home() / ".config" / "clawbench" / "notify.toml"

Post = Callable[[str, str], None]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NotifyConfig:
    webhook_url: str | None = None
    interval_s: float = DEFAULT_INTERVAL_S
    heartbeat_every: int = 0
    stall_timeout_s: float = DEFAULT_STALL_TIMEOUT_S


def load_config(path: Path = CONFIG_PATH) -> NotifyConfig:
    """Read ``notify.toml``; a missing or empty file means defaults."""
    if not path.is_file():
        return NotifyConfig()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise SystemExit(f"ERROR: cannot read {path}: {e}") from None
    return NotifyConfig(
        webhook_url=raw.get("webhook_url") or None,
        interval_s=float(raw.get("interval_s", DEFAULT_INTERVAL_S)),
        heartbeat_every=int(raw.get("heartbeat_every", 0)),
        stall_timeout_s=float(raw.get("stall_timeout_s", DEFAULT_STALL_TIMEOUT_S)),
    )


# ---------------------------------------------------------------------------
# Reading the batch directory
# ---------------------------------------------------------------------------


@dataclass
class BatchSnapshot:
    done: int = 0
    passed: int = 0
    intercepted: int = 0
    last_case: str | None = None
    last_activity: float = 0.0
    started: float | None = None
    finished: bool = False
    summary: dict[str, Any] = field(default_factory=dict)


def snapshot(batch_dir: Path) -> BatchSnapshot:
    snap = BatchSnapshot()
    summary_file = batch_dir / "batch-summary.json"
    if summary_file.is_file():
        snap.finished = True
        try:
            snap.summary = json.loads(summary_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            snap.summary = {}

    newest: tuple[float, str | None] = (0.0, None)
    for meta_file in batch_dir.glob("*/*/run-meta.json"):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            mtime = meta_file.stat().st_mtime
        except (OSError, json.JSONDecodeError):
            continue
        snap.done += 1
        if meta.get("intercepted"):
            snap.intercepted += 1
        if meta.get("judge_match") is True:
            snap.passed += 1
        if mtime > newest[0]:
            newest = (mtime, meta.get("test_case") or meta_file.parent.name)
    snap.last_case = newest[1]

    activity = [newest[0]]
    starts: list[float] = []
    for log_file in (batch_dir / "batch-logs").glob("*.log"):
        try:
            stat = log_file.stat()
        except OSError:
            continue
        activity.append(stat.st_mtime)
        starts.append(stat.st_mtime)
    try:
        starts.append(batch_dir.stat().st_mtime)
    except OSError:
        pass
    snap.last_activity = max(activity)
    snap.started = min(starts) if starts else None
    return snap


def error_tail(batch_dir: Path, lines: int = 15) -> str:
    """Last lines of the most recently written batch log — where the abort is."""
    logs = sorted(
        (batch_dir / "batch-logs").glob("*.log"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
    )
    if not logs:
        return ""
    try:
        text = logs[-1].read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:])


def pid_alive(pid: int) -> bool:
    """Whether ``pid`` is still running.

    Not ``os.kill(pid, 0)``: on Windows that call *terminates* the process,
    because any signal other than the Ctrl events is passed to
    TerminateProcess as an exit code.
    """
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        process_query_limited_information = 0x1000
        still_active = 259
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------


def post_webhook(url: str, text: str) -> None:
    """POST a message; Slack reads ``text``, Discord reads ``content``."""
    payload = json.dumps({"text": text, "content": text}).encode()
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            pass
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # A failed notification must not take the watcher down with it.
        print(f"[watch] webhook post failed: {e}", file=sys.stderr)


def _fmt_hours(seconds: float) -> str:
    return f"{seconds / 3600:.1f}h"


def completion_message(name: str, snap: BatchSnapshot, now: float) -> str:
    totals = snap.summary.get("totals") or {}
    elapsed = snap.summary.get("elapsed_seconds")
    if not isinstance(elapsed, (int, float)):
        elapsed = now - snap.started if snap.started else 0
    jobs = snap.summary.get("jobs")
    total = len(jobs) if isinstance(jobs, list) else snap.done
    passed = totals.get("passed", snap.passed)
    errors = totals.get("error", 0)
    text = f"✅ {name} · finished · {passed}/{total} passed · {_fmt_hours(elapsed)}"
    if errors:
        text += f" · {errors} infra error(s)"
    return text


def abort_message(
    name: str, snap: BatchSnapshot, now: float, reason: str, tail: str
) -> str:
    elapsed = now - snap.started if snap.started else 0
    text = (
        f"🛑 {name} · aborted ({reason}) · {snap.done} done · "
        f"last task {snap.last_case or '?'} · {_fmt_hours(elapsed)} elapsed"
    )
    if tail:
        text += f"\n```\n{tail}\n```"
    return text


def heartbeat_message(
    name: str, snap: BatchSnapshot, now: float, total: int | None
) -> str:
    elapsed = now - snap.started if snap.started else 0
    denominator = f"/{total}" if total else ""
    return (
        f"💓 {name} · {snap.done}{denominator} done · {_fmt_hours(elapsed)} elapsed · "
        f"{snap.passed} passes · {snap.intercepted} intercepted"
    )


# ---------------------------------------------------------------------------
# The watch loop
# ---------------------------------------------------------------------------


@dataclass
class Watcher:
    batch_dir: Path
    config: NotifyConfig
    pid: int | None = None
    total: int | None = None
    post: Post = post_webhook
    now: Callable[[], float] = time.time
    log: Callable[[str], None] = print
    _last_heartbeat_at: int = 0

    @property
    def name(self) -> str:
        return self.batch_dir.name

    def _notify(self, text: str) -> None:
        self.log(text)
        if self.config.webhook_url:
            self.post(self.config.webhook_url, text)

    def poll(self) -> int | None:
        """One observation. Returns an exit status once the batch is over."""
        snap = snapshot(self.batch_dir)
        now = self.now()

        if snap.finished:
            self._notify(completion_message(self.name, snap, now))
            return 0

        if self.pid is not None and not pid_alive(self.pid):
            reason = f"pid {self.pid} exited without a batch summary"
            self._notify(
                abort_message(self.name, snap, now, reason, error_tail(self.batch_dir))
            )
            return 1

        if (
            snap.last_activity
            and now - snap.last_activity > self.config.stall_timeout_s
        ):
            quiet = _fmt_hours(now - snap.last_activity)
            reason = f"no artifact activity for {quiet}"
            self._notify(
                abort_message(self.name, snap, now, reason, error_tail(self.batch_dir))
            )
            return 1

        every = self.config.heartbeat_every
        if every > 0 and snap.done // every > self._last_heartbeat_at // every:
            self._last_heartbeat_at = snap.done
            self._notify(heartbeat_message(self.name, snap, now, self.total))
        return None

    def run(self, sleep: Callable[[float], None] = time.sleep) -> int:
        while True:
            status = self.poll()
            if status is not None:
                return status
            sleep(self.config.interval_s)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawbench-batch-watch",
        description=(
            "Poll a running batch directory and post to a webhook when it "
            "aborts or finishes."
        ),
    )
    parser.add_argument("batch_dir", type=Path, help="the batch-<timestamp> directory")
    parser.add_argument(
        "--webhook", help="Slack/Discord webhook URL (overrides notify.toml)"
    )
    parser.add_argument(
        "--interval", type=float, help="seconds between polls (default: 60)"
    )
    parser.add_argument(
        "--heartbeat-every",
        type=int,
        help="post a progress line every N completed tasks (default: off)",
    )
    parser.add_argument(
        "--stall-timeout",
        type=float,
        help="seconds without artifact activity before declaring an abort (default: 2700)",
    )
    parser.add_argument(
        "--pid", type=int, help="batch process id; its exit means abort"
    )
    parser.add_argument(
        "--total", type=int, help="expected job count, for heartbeat denominators"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help=f"notify.toml to read (default: {CONFIG_PATH})",
    )
    parser.add_argument("--once", action="store_true", help="poll once and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.batch_dir.is_dir():
        print(f"ERROR: not a directory: {args.batch_dir}", file=sys.stderr)
        return 2
    base = load_config(args.config)
    config = NotifyConfig(
        webhook_url=args.webhook or base.webhook_url,
        interval_s=args.interval if args.interval is not None else base.interval_s,
        heartbeat_every=(
            args.heartbeat_every
            if args.heartbeat_every is not None
            else base.heartbeat_every
        ),
        stall_timeout_s=(
            args.stall_timeout
            if args.stall_timeout is not None
            else base.stall_timeout_s
        ),
    )
    if not config.webhook_url:
        print(
            "[watch] no webhook configured; printing notifications only "
            f"(set webhook_url in {args.config} or pass --webhook)"
        )
    watcher = Watcher(
        batch_dir=args.batch_dir.resolve(),
        config=config,
        pid=args.pid,
        total=args.total,
    )
    if args.once:
        status = watcher.poll()
        return 0 if status is None else status
    return watcher.run()


if __name__ == "__main__":
    raise SystemExit(main())
