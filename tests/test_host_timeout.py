"""Host-side deadlines: a wedged container must not stall a run or a batch."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

from clawbench.runner.batch import job_timeout_s, stop_wedged_job
from clawbench.utils.timeouts import (
    BATCH_JOB_GRACE_S,
    DEFAULT_TIME_LIMIT_S,
    HOST_TIMEOUT_GRACE_S,
)


def _import_docker(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """docker.py resolves a container engine at import time."""
    import importlib

    for name in (
        "clawbench.runner.run_support.docker",
        "clawbench.runner.run_support.config",
    ):
        sys.modules.pop(name, None)
    monkeypatch.delenv("CONTAINER_ENGINE", raising=False)
    monkeypatch.setattr(shutil, "which", lambda cmd: cmd if cmd == "docker" else None)
    return importlib.import_module("clawbench.runner.run_support.docker")


# --- per-job bound in batch.py ------------------------------------------------


def test_job_timeout_reads_the_time_limit_from_a_task_directory(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.json").write_text(json.dumps({"time_limit": 12}))

    assert job_timeout_s(tmp_path) == 12 * 60 + BATCH_JOB_GRACE_S


def test_job_timeout_reads_a_flat_claw_eval_task_file(tmp_path: Path) -> None:
    """claw-eval stores tasks as flat <suite>/<id>.json, not <dir>/task.json."""
    flat = tmp_path / "ce-T001-example.json"
    flat.write_text(json.dumps({"time_limit": 5}))

    assert job_timeout_s(flat) == 5 * 60 + BATCH_JOB_GRACE_S


@pytest.mark.parametrize(
    "payload",
    ["", "not json", json.dumps({}), json.dumps({"time_limit": "soon"})],
    ids=["empty", "garbage", "no-time-limit", "non-numeric"],
)
def test_job_timeout_falls_back_when_the_task_is_unreadable(
    tmp_path: Path, payload: str
) -> None:
    (tmp_path / "task.json").write_text(payload)

    assert job_timeout_s(tmp_path) == DEFAULT_TIME_LIMIT_S + BATCH_JOB_GRACE_S


def test_job_timeout_override_and_disable(tmp_path: Path) -> None:
    (tmp_path / "task.json").write_text(json.dumps({"time_limit": 1}))

    assert job_timeout_s(tmp_path, 30) == 1800
    assert job_timeout_s(tmp_path, 0) is None  # explicitly disabled


def test_batch_job_bound_exceeds_the_runs_own_deadline() -> None:
    """The batch bound is a backstop: clawbench-run must hit its own first."""
    assert BATCH_JOB_GRACE_S > HOST_TIMEOUT_GRACE_S


def test_batch_stays_importable_without_a_container_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """batch.py takes its deadlines from utils.timeouts, not run_support.docker,
    which resolves a container engine at import time and exits without one."""
    import importlib

    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    sys.modules.pop("clawbench.runner.batch", None)

    batch = importlib.import_module("clawbench.runner.batch")

    assert batch.job_timeout_s is not None
    assert "clawbench.runner.run_support.docker" not in sys.modules


def test_wait_for_actually_bounds_a_hanging_child() -> None:
    """Guard the mechanism itself: asyncio.wait_for must interrupt the wait."""

    async def scenario() -> bool:
        async def never_returns() -> None:
            await asyncio.sleep(3600)

        try:
            await asyncio.wait_for(never_returns(), timeout=0.05)
        except asyncio.TimeoutError:
            return True
        return False

    assert asyncio.run(scenario()) is True


# --- docker_wait deadline -----------------------------------------------------


class _NeverExits:
    """Stand-in for `docker wait` against a container that never exits."""

    pid = 4242

    def poll(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        raise subprocess.TimeoutExpired("docker wait", timeout or 0)

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass


def test_docker_wait_kills_the_container_when_the_deadline_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker = _import_docker(monkeypatch)

    monkeypatch.setattr(docker.subprocess, "Popen", lambda *a, **k: _NeverExits())
    monkeypatch.setattr(docker, "_container_usage_summary", lambda *a, **k: None)

    calls: list[list[str]] = []

    def fake_run(cmd, *a, **k):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(docker.subprocess, "run", fake_run)

    started = time.time()
    timed_out = docker.docker_wait("wedged-container", timeout_s=0.2)

    assert timed_out is True
    assert time.time() - started < 30  # returned promptly, did not hang
    assert any(c[1:] == ["kill", "wedged-container"] for c in calls), calls


def test_docker_wait_without_a_deadline_still_waits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """timeout_s=None keeps the old unbounded behaviour (--human runs)."""
    docker = _import_docker(monkeypatch)

    class ExitsOnSecondPoll:
        pid = 1
        polls = 0

        def poll(self):  # type: ignore[no-untyped-def]
            ExitsOnSecondPoll.polls += 1
            return None if ExitsOnSecondPoll.polls < 2 else 0

        def wait(self, timeout: float | None = None) -> int:
            return 0

    monkeypatch.setattr(docker.subprocess, "Popen", lambda *a, **k: ExitsOnSecondPoll())
    monkeypatch.setattr(docker, "_container_usage_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        docker.subprocess,
        "run",
        lambda cmd, *a, **k: subprocess.CompletedProcess(cmd, 1, "", ""),
    )

    assert docker.docker_wait("healthy-container", timeout_s=None) is False


# --- stopping a wedged job without orphaning its container --------------------


posix_kill_only = pytest.mark.skipif(
    not hasattr(signal, "SIGKILL"),
    reason="the batch kill path is os.killpg + SIGKILL, neither of which "
    "exists on Windows; the runner does not use it there either",
)


class _FakeRun:
    """Stand-in for a wedged clawbench-run: exits only on signals it honours.

    SIGTERM is catchable and run.py handles it (raising KeyboardInterrupt so
    the `finally: docker_rm(container)` runs); SIGKILL is not. A stub that
    honours only some signals is what makes the difference observable.
    """

    def __init__(self, honours: set[int], output: bytes = b"") -> None:
        self.honours = honours
        self.output = output
        self.signals: list[int] = []
        self.pid = 31337
        self._exited: asyncio.Event | None = None

    def _event(self) -> asyncio.Event:
        if self._exited is None:
            self._exited = asyncio.Event()
        return self._exited

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        await self._event().wait()
        return self.output, b""

    def deliver(self, sig: int) -> None:
        self.signals.append(sig)
        if sig in self.honours:
            self._event().set()


def _run_stop(
    proc: _FakeRun, monkeypatch: pytest.MonkeyPatch, grace_s: float = 0.05
) -> tuple[bytes, bool]:
    # raising=False: os.killpg is POSIX-only and absent on Windows, where the
    # batch driver's kill path does not run either.
    monkeypatch.setattr(
        os,
        "killpg",
        lambda pid, sig: proc.deliver(sig) if pid == proc.pid else None,
        raising=False,
    )
    return asyncio.run(stop_wedged_job(proc, grace_s=grace_s))


@posix_kill_only
def test_a_timed_out_job_is_asked_to_stop_before_it_is_killed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SIGKILL cannot be caught, so killing the group outright reaps the
    Python child and leaves its container running under the engine daemon.
    The first signal must be one clawbench-run can act on."""
    proc = _FakeRun(honours={signal.SIGTERM}, output=b"partial log\n")

    stdout, escalated = _run_stop(proc, monkeypatch)

    assert proc.signals == [signal.SIGTERM]
    assert signal.SIGKILL not in proc.signals
    assert escalated is False
    assert stdout == b"partial log\n"


@posix_kill_only
def test_a_job_that_ignores_sigterm_is_still_killed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Graceful teardown must not become a second way to hang the batch."""
    proc = _FakeRun(honours=set())

    _, escalated = _run_stop(proc, monkeypatch)

    assert proc.signals == [signal.SIGTERM, signal.SIGKILL]
    assert escalated is True


@posix_kill_only
def test_escalation_is_reported_so_the_job_log_can_say_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A SIGKILLed run skipped its own cleanup, so the log must not claim the
    container was removed. The flag is what lets batch.py tell them apart."""
    graceful = _FakeRun(honours={signal.SIGTERM})
    stubborn = _FakeRun(honours={signal.SIGKILL})

    assert _run_stop(graceful, monkeypatch)[1] is False
    assert _run_stop(stubborn, monkeypatch)[1] is True


@posix_kill_only
def test_an_already_dead_job_is_not_reported_as_escalated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the group is gone the run finished its own teardown; saying it was
    SIGKILLed would send a reader hunting for a container that isn't there."""
    proc = _FakeRun(honours=set())

    def gone(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(os, "killpg", gone, raising=False)

    stdout, escalated = asyncio.run(stop_wedged_job(proc, grace_s=0.05))

    assert escalated is False
    assert stdout == b""
