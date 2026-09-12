"""`clawbench-batch --auto-restart` and `clawbench-batch-watch` (#160)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from clawbench.runner import supervise, watch

# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------


def _fake_spawn(exit_codes: list[int]) -> tuple[list[list[str]], supervise.Spawn]:
    """A child that exits with each code in turn, recording every command."""
    calls: list[list[str]] = []
    remaining = list(exit_codes)

    def spawn(cmd: list[str]) -> int:
        calls.append(list(cmd))
        return remaining.pop(0)

    return calls, spawn


def test_supervisor_restarts_into_the_same_batch_dir_until_success(
    tmp_path: Path,
) -> None:
    calls, spawn = _fake_spawn([1, 137, 0])
    sleeps: list[float] = []
    lines: list[str] = []

    rc = supervise.run_supervised(
        ["--models", "m", "--all-cases"],
        batch_dir=tmp_path / "batch-x",
        max_restarts=3,
        delay_s=30,
        spawn=spawn,
        sleep=sleeps.append,
        log=lines.append,
    )

    assert rc == 0
    assert len(calls) == 3
    for cmd in calls:
        assert cmd[:3] == [sys.executable, "-m", supervise.BATCH_MODULE]
        assert cmd[-2:] == ["--resume", str(tmp_path / "batch-x")]
        assert "--auto-restart" not in cmd
    # Waited before each retry, never after the success.
    assert sleeps == [30, 30]
    assert any("finished cleanly on attempt 3" in line for line in lines)


def test_supervisor_gives_up_after_n_restarts(tmp_path: Path) -> None:
    calls, spawn = _fake_spawn([1, 1, 1, 1])
    lines: list[str] = []

    rc = supervise.run_supervised(
        [],
        batch_dir=tmp_path,
        max_restarts=2,
        spawn=spawn,
        sleep=lambda _s: None,
        log=lines.append,
    )

    assert rc == 1
    # N restarts means N+1 attempts, no more.
    assert len(calls) == 3
    assert any("giving up after 3 attempt(s)" in line for line in lines)
    assert any(f"--resume {tmp_path}" in line for line in lines)


def test_supervisor_does_not_restart_after_operator_interrupt(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def spawn(cmd: list[str]) -> int:
        calls.append(cmd)
        raise KeyboardInterrupt

    rc = supervise.run_supervised(
        [],
        batch_dir=tmp_path,
        max_restarts=5,
        spawn=spawn,
        sleep=lambda _s: pytest.fail("must not sleep after an interrupt"),
        log=lambda _line: None,
    )

    assert rc == supervise.INTERRUPTED
    assert len(calls) == 1


def test_supervisor_flags_are_stripped_from_the_child_command() -> None:
    argv = [
        "--models",
        "m",
        "--auto-restart",
        "3",
        "--auto-restart-delay=5",
        "--resume",
        "/old/batch",
        "--all-cases",
    ]

    assert supervise.strip_supervisor_flags(argv) == ["--models", "m", "--all-cases"]


def test_resolve_batch_dir_creates_a_fresh_dir_or_reuses_resume(tmp_path: Path) -> None:
    fresh = supervise.resolve_batch_dir(None, tmp_path / "out")
    assert fresh.is_dir()
    assert fresh.parent == (tmp_path / "out").resolve()
    assert fresh.name.startswith("batch-")

    existing = tmp_path / "existing"
    assert (
        supervise.resolve_batch_dir(str(existing), tmp_path / "out")
        == existing.resolve()
    )


def test_batch_cli_hands_off_to_the_supervisor(tmp_path: Path) -> None:
    """`--auto-restart N` never runs the batch in-process."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    code = (
        "import sys\n"
        "from clawbench.runner import batch, supervise\n"
        "seen = {}\n"
        "def fake(argv, *, batch_dir, max_restarts, delay_s):\n"
        "    seen.update(argv=argv, batch_dir=str(batch_dir), n=max_restarts, d=delay_s)\n"
        "    return 7\n"
        "supervise.run_supervised = fake\n"
        f"sys.argv = ['clawbench-batch', '--models', 'm', '--all-cases', "
        f"'--output-dir', {str(tmp_path)!r}, '--auto-restart', '2', "
        "'--auto-restart-delay', '1']\n"
        "try:\n"
        "    batch.main()\n"
        "except SystemExit as e:\n"
        "    print('rc', e.code)\n"
        "print(seen)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "rc 7" in result.stdout
    assert "'n': 2" in result.stdout and "'d': 1.0" in result.stdout
    assert "--auto-restart" not in result.stdout.split("'argv': ")[1].split("]")[0]
    assert "batch-" in result.stdout


# ---------------------------------------------------------------------------
# Watcher
# ---------------------------------------------------------------------------


def _run(
    base: Path,
    model: str,
    case: str,
    *,
    intercepted: bool,
    judge_match: object = "absent",
) -> Path:
    run_dir = base / model / case
    run_dir.mkdir(parents=True)
    meta: dict = {"test_case": case, "model": model, "intercepted": intercepted}
    if judge_match != "absent":
        meta["judge_match"] = judge_match
    (run_dir / "run-meta.json").write_text(json.dumps(meta))
    return run_dir


def _batch(tmp_path: Path) -> Path:
    base = tmp_path / "batch-20260912-000000"
    (base / "batch-logs").mkdir(parents=True)
    (base / "batch-logs" / "case-1-m.log").write_text("started\nok\n")
    _run(base, "m", "case-1", intercepted=True, judge_match=True)
    _run(base, "m", "case-2", intercepted=True, judge_match=False)
    _run(base, "m", "case-3", intercepted=False)
    return base


def _watcher(
    base: Path,
    *,
    heartbeat_every: int = 0,
    stall_timeout_s: float = 3600,
    now: float | None = None,
    pid: int | None = None,
    total: int | None = None,
) -> tuple[watch.Watcher, list[tuple[str, str]]]:
    posts: list[tuple[str, str]] = []
    cfg = watch.NotifyConfig(
        webhook_url="https://hooks.example.test/x",
        interval_s=1,
        heartbeat_every=heartbeat_every,
        stall_timeout_s=stall_timeout_s,
    )
    clock = now if now is not None else base.stat().st_mtime + 60
    watcher = watch.Watcher(
        batch_dir=base,
        config=cfg,
        pid=pid,
        total=total,
        post=lambda url, text: posts.append((url, text)),
        now=lambda: clock,
        log=lambda _line: None,
    )
    return watcher, posts


def test_snapshot_counts_both_stages_and_finds_the_last_task(tmp_path: Path) -> None:
    snap = watch.snapshot(_batch(tmp_path))

    assert snap.done == 3
    assert snap.intercepted == 2
    assert snap.passed == 1
    assert snap.last_case in {"case-1", "case-2", "case-3"}
    assert snap.finished is False
    assert snap.started is not None and snap.last_activity >= snap.started


def test_watcher_keeps_quiet_while_the_batch_is_healthy(tmp_path: Path) -> None:
    watcher, posts = _watcher(_batch(tmp_path))

    assert watcher.poll() is None
    assert posts == []


def test_watcher_posts_on_completion(tmp_path: Path) -> None:
    base = _batch(tmp_path)
    (base / "batch-summary.json").write_text(
        json.dumps(
            {
                "elapsed_seconds": 7200,
                "jobs": [{}] * 3,
                "totals": {"passed": 1, "failed": 2, "error": 0},
            }
        )
    )
    watcher, posts = _watcher(base)

    assert watcher.poll() == 0
    ((url, text),) = posts
    assert url == "https://hooks.example.test/x"
    assert "finished" in text and "1/3 passed" in text and "2.0h" in text


def test_watcher_posts_abort_when_the_pid_is_gone(tmp_path: Path) -> None:
    base = _batch(tmp_path)
    (base / "batch-logs" / "case-1-m.log").write_text("started\nTraceback: boom\n")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    watcher, posts = _watcher(base, pid=dead.pid)

    assert watcher.poll() == 1
    ((_url, text),) = posts
    assert "aborted" in text and f"pid {dead.pid}" in text
    assert "3 done" in text
    assert "Traceback: boom" in text


def test_watcher_posts_abort_on_stall(tmp_path: Path) -> None:
    base = _batch(tmp_path)
    stale_now = base.stat().st_mtime + 10 * 3600
    watcher, posts = _watcher(base, stall_timeout_s=3600, now=stale_now)

    assert watcher.poll() == 1
    ((_url, text),) = posts
    assert "no artifact activity" in text


def test_watcher_heartbeats_every_n_tasks_without_repeating(tmp_path: Path) -> None:
    base = _batch(tmp_path)
    watcher, posts = _watcher(base, heartbeat_every=2, total=10)

    assert watcher.poll() is None
    assert len(posts) == 1
    assert "3/10 done" in posts[0][1]
    # Same count again: no second heartbeat until another 2 tasks land.
    assert watcher.poll() is None
    assert len(posts) == 1
    _run(base, "m", "case-4", intercepted=True)
    assert watcher.poll() is None
    assert len(posts) == 2


def test_pid_alive_for_this_process_and_a_dead_one() -> None:
    assert watch.pid_alive(os.getpid()) is True
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    assert watch.pid_alive(dead.pid) is False


def test_notify_config_reads_toml_and_flags_override(tmp_path: Path) -> None:
    cfg_file = tmp_path / "notify.toml"
    cfg_file.write_text(
        'webhook_url = "https://hooks.example.test/from-file"\n'
        "interval_s = 15\nheartbeat_every = 5\n"
    )
    cfg = watch.load_config(cfg_file)
    assert cfg.webhook_url == "https://hooks.example.test/from-file"
    assert cfg.interval_s == 15
    assert cfg.heartbeat_every == 5
    assert cfg.stall_timeout_s == watch.DEFAULT_STALL_TIMEOUT_S

    assert watch.load_config(tmp_path / "missing.toml") == watch.NotifyConfig()


def test_watch_cli_once_reports_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = _batch(tmp_path)
    (base / "batch-summary.json").write_text(
        json.dumps({"elapsed_seconds": 60, "jobs": [{}] * 3, "totals": {"passed": 1}})
    )

    rc = watch.main([str(base), "--once", "--config", str(tmp_path / "none.toml")])

    assert rc == 0
    out = capsys.readouterr().out
    assert "no webhook configured" in out
    assert "finished" in out


def test_watch_cli_rejects_a_missing_dir(tmp_path: Path) -> None:
    assert watch.main([str(tmp_path / "nope"), "--once"]) == 2
