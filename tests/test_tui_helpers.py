"""Executable host-side tests for TUI helper behavior."""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from clawbench import tui


class _TTY:
    def __init__(self, is_tty: bool) -> None:
        self._is_tty = is_tty
        self.output = ""

    def isatty(self) -> bool:
        return self._is_tty

    def write(self, text: str) -> int:
        self.output += text
        return len(text)

    def flush(self) -> None:
        return None


class _Prompt:
    def __init__(self, value: object) -> None:
        self._value = value

    def ask(self) -> object:
        return self._value


class _QuestionaryDriver:
    def __init__(
        self,
        *,
        select: list[object] | None = None,
        checkbox: list[object] | None = None,
        text: list[object] | None = None,
        confirm: list[object] | None = None,
    ) -> None:
        self._answers = {
            "select": list(select or []),
            "checkbox": list(checkbox or []),
            "text": list(text or []),
            "confirm": list(confirm or []),
        }

    def select(self, *_args: object, **_kwargs: object) -> _Prompt:
        return _Prompt(self._pop("select"))

    def checkbox(self, *_args: object, **_kwargs: object) -> _Prompt:
        return _Prompt(self._pop("checkbox"))

    def text(self, *_args: object, **_kwargs: object) -> _Prompt:
        return _Prompt(self._pop("text"))

    def confirm(self, *_args: object, **_kwargs: object) -> _Prompt:
        return _Prompt(self._pop("confirm"))

    def assert_done(self) -> None:
        leftovers = {k: v for k, v in self._answers.items() if v}
        assert leftovers == {}

    def _pop(self, kind: str) -> object:
        assert self._answers[kind], f"no queued {kind} answer"
        return self._answers[kind].pop(0)


def _install_tui_main_fakes(
    monkeypatch: pytest.MonkeyPatch,
    driver: _QuestionaryDriver,
) -> list[list[str]]:
    commands: list[list[str]] = []
    cases_by_dir = {
        "test-cases/v1": [
            "001-daily-life-food-uber-eats",
            "002-daily-life-shopping-amazon",
        ],
        "test-cases/v2": [
            "v2-0001-daily-life-food-uber-eats",
            "v2-0002-daily-life-shopping-amazon",
        ],
        "test-cases/v1-lite": ["001-daily-life-food-uber-eats"],
        "test-cases/claw-eval": ["ce-T050-regulatory-research"],
    }

    monkeypatch.setattr(tui.sys, "argv", ["clawbench"])
    monkeypatch.setattr(tui, "_require_tty", lambda: None)
    monkeypatch.setattr(tui, "ensure_workspace_templates", lambda: None)
    monkeypatch.setattr(tui.os, "chdir", lambda _path: None)
    monkeypatch.setattr(tui, "_load_saved_theme", lambda: "dark")
    monkeypatch.setattr(tui, "load_models", lambda: ["model-a"])
    monkeypatch.setattr(tui, "_check_engine", lambda: ("docker", "ready", ""))
    monkeypatch.setattr(
        tui,
        "_fix_engine",
        lambda *_args: pytest.fail("engine fix should not run in TUI flow tests"),
    )
    monkeypatch.setattr(tui, "load_cases", lambda cases_dir: cases_by_dir[cases_dir])
    monkeypatch.setattr(tui, "_recommend_concurrent", lambda: 2)
    monkeypatch.setattr(tui.questionary, "select", driver.select)
    monkeypatch.setattr(tui.questionary, "checkbox", driver.checkbox)
    monkeypatch.setattr(tui.questionary, "text", driver.text)
    monkeypatch.setattr(tui.questionary, "confirm", driver.confirm)
    monkeypatch.setattr(
        tui,
        "run_cmd",
        lambda cmd, **_kwargs: commands.append(cmd),
    )
    return commands


def test_tui_dataset_and_case_helpers_use_known_suites() -> None:
    assert tui._dataset_cases_dir_name("v2") == "test-cases/v2"
    assert "V2" in tui._dataset_summary("v2")
    assert tui._case_numeric_id("v2-1065b-daily-life-home-services-handy") == 1065
    assert (
        tui._case_display("v2-1065b-daily-life-home-services-handy")
        == "1065b  v2-1065b-daily-life-home-services-handy"
    )


def test_tui_load_cases_reads_flat_and_directory_suites() -> None:
    v1_cases = tui.load_cases("test-cases/v1")
    claw_eval_cases = tui.load_cases("test-cases/claw-eval")

    assert "001-daily-life-food-uber-eats" in v1_cases
    assert "ce-T050-regulatory-research" in claw_eval_cases


def test_tui_theme_save_and_load_round_trips(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "clawbench-config"
    config_file = config_dir / "tui.json"
    monkeypatch.setattr(tui, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(tui, "CONFIG_FILE", config_file)

    assert tui._load_saved_theme() is None
    tui._save_theme("light")
    assert tui._load_saved_theme() == "light"
    config_file.write_text('{"theme": "invalid"}', encoding="utf-8")
    assert tui._load_saved_theme() is None


def test_tui_require_tty_exits_for_non_interactive_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tui.sys, "stdin", _TTY(False))
    monkeypatch.setattr(tui.sys, "stdout", _TTY(False))

    with pytest.raises(SystemExit) as exc:
        tui._require_tty()

    assert exc.value.code == 1


def test_tui_engine_detection_prefers_env_then_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONTAINER_ENGINE", "podman")
    monkeypatch.setattr(
        tui.shutil, "which", lambda cmd: cmd if cmd == "podman" else None
    )
    assert tui._engine_from_env_or_path() == "podman"

    monkeypatch.setenv("CONTAINER_ENGINE", "docker")
    assert tui._engine_from_env_or_path() == "podman"

    monkeypatch.delenv("CONTAINER_ENGINE", raising=False)
    monkeypatch.setattr(tui.shutil, "which", lambda cmd: cmd)
    assert tui._engine_from_env_or_path() == "docker"

    monkeypatch.setattr(tui.shutil, "which", lambda _cmd: None)
    assert tui._engine_from_env_or_path() is None


def test_tui_check_engine_classifies_docker_ready_and_not_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tui, "_engine_from_env_or_path", lambda: "docker")

    def ready_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        assert cmd == ["docker", "info"]
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(tui.subprocess, "run", ready_run)
    assert tui._check_engine() == ("docker", "ready", "")

    def failed_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        assert cmd == ["docker", "info"]
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="daemon down")

    monkeypatch.setattr(tui.subprocess, "run", failed_run)
    assert tui._check_engine() == ("docker", "docker_not_running", "daemon down")


def test_tui_check_engine_classifies_podman_machine_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tui, "_engine_from_env_or_path", lambda: "podman")
    monkeypatch.setattr(tui.platform, "system", lambda: "Windows")
    calls: list[list[str]] = []

    def no_machine_run(
        cmd: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")

    monkeypatch.setattr(tui.subprocess, "run", no_machine_run)
    assert tui._check_engine() == ("podman", "podman_no_machine", "")
    assert calls == [["podman", "machine", "list", "--format", "json"]]

    def low_memory_run(
        cmd: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess:
        if cmd == ["podman", "machine", "list", "--format", "json"]:
            return subprocess.CompletedProcess(
                cmd, 0, stdout='[{"Running": true}]', stderr=""
            )
        if cmd == ["podman", "ps"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="2048", stderr="")

    monkeypatch.setattr(tui.subprocess, "run", low_memory_run)
    assert tui._check_engine() == ("podman", "podman_low_memory", "2048")


def test_tui_recommend_concurrent_returns_positive_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tui.multiprocessing, "cpu_count", lambda: 8)

    assert tui._recommend_concurrent() >= 1


def test_tui_recommend_concurrent_uses_windows_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tui.platform, "system", lambda: "Windows")
    monkeypatch.setattr(tui.multiprocessing, "cpu_count", lambda: 16)
    monkeypatch.setattr(tui, "_windows_physical_memory_gb", lambda: 4)

    assert tui._recommend_concurrent() == 2


def test_tui_windows_physical_memory_uses_global_memory_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Kernel32:
        def GlobalMemoryStatusEx(self, status: Any) -> int:
            status.ullTotalPhys = 12 * 1024**3
            return 1

    fake_ctypes: Any = types.ModuleType("ctypes")
    fake_ctypes.Structure = object
    fake_ctypes.c_ulong = object()
    fake_ctypes.c_ulonglong = object()
    fake_ctypes.sizeof = lambda _status: 64
    fake_ctypes.byref = lambda status: status
    fake_ctypes.windll = types.SimpleNamespace(kernel32=Kernel32())
    monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)

    assert tui._windows_physical_memory_gb() == 12


def test_tui_physical_memory_falls_back_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tui.platform, "system", lambda: "Windows")
    monkeypatch.setattr(tui, "_windows_physical_memory_gb", lambda: None)
    monkeypatch.delattr(tui.os, "sysconf", raising=False)

    assert tui._physical_memory_gb() == 8


def test_tui_main_single_run_flow_builds_runner_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _QuestionaryDriver(
        select=[
            "v1",
            "single",
            "model-a",
            "codex",
            "001-daily-life-food-uber-eats",
            "exit",
        ],
        confirm=[True],
    )
    commands = _install_tui_main_fakes(monkeypatch, driver)

    tui.main()

    assert commands == [
        [
            sys.executable,
            "-m",
            "clawbench.runner.run",
            "test-cases/v1/001-daily-life-food-uber-eats",
            "model-a",
            "--harness",
            "codex",
        ]
    ]
    driver.assert_done()


def test_tui_main_batch_range_flow_builds_dry_run_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _QuestionaryDriver(
        select=["v2", "batch", "openclaw", "range", "exit"],
        checkbox=[["model-a"]],
        text=["1-2", "3"],
        confirm=[True, True],
    )
    commands = _install_tui_main_fakes(monkeypatch, driver)

    tui.main()

    assert commands == [
        [
            sys.executable,
            "-m",
            "clawbench.runner.batch",
            "--models",
            "model-a",
            "--cases-suite",
            "v2",
            "--case-range",
            "1-2",
            "--max-concurrent",
            "3",
            "--harness",
            "openclaw",
            "--dry-run",
        ]
    ]
    driver.assert_done()


def test_tui_main_dataset_switch_then_human_flow_builds_runner_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = _QuestionaryDriver(
        select=[
            "v1",
            "dataset",
            "claw-eval",
            "human",
            "ce-T050-regulatory-research",
            "exit",
        ],
        confirm=[True],
    )
    commands = _install_tui_main_fakes(monkeypatch, driver)

    tui.main()

    assert commands == [
        [
            sys.executable,
            "-m",
            "clawbench.runner.run",
            "test-cases/claw-eval/ce-T050-regulatory-research",
            "--human",
        ]
    ]
    driver.assert_done()
