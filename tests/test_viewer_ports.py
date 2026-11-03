"""Local viewer ports are allocated by the engine, not a temporary socket."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _start(
    docker: ModuleType,
    mode: str,
    tmp_path: Path,
    host_port: int | None = None,
    browser_mode: str = "local",
) -> int | None:
    schema = tmp_path / "schema.json"
    schema.write_text("{}")
    info = tmp_path / "info"
    info.mkdir(exist_ok=True)
    kwargs = {"host_port": host_port, "browser_mode": browser_mode}
    if mode == "human":
        return docker.docker_run_human(
            "owned-viewer", "Synthetic task", schema, info, **kwargs
        )
    return docker.docker_run(
        "owned-viewer",
        "Synthetic task",
        schema,
        info,
        {
            "model": "synthetic",
            "base_url": "http://example.test",
            "api_type": "openai",
        },
        **kwargs,
    )


@pytest.mark.parametrize("engine", ["docker", "podman"])
@pytest.mark.parametrize("mode", ["human", "agent"])
def test_engine_allocates_loopback_viewer_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, engine: str, mode: str
) -> None:
    docker = importlib.import_module("clawbench.runner.run_support.docker")
    monkeypatch.setattr(docker, "engine", lambda: engine)
    commands: list[list[str]] = []

    def invoke(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        if cmd[1] == "port":
            assert kwargs["timeout"] == 10
            assert kwargs["check"] is True
        return subprocess.CompletedProcess(cmd, 0, stdout="127.0.0.1:49153\n")

    monkeypatch.setattr(docker.subprocess, "run", invoke)

    assert _start(docker, mode, tmp_path) == 49153
    assert commands[0][commands[0].index("-p") + 1] == "127.0.0.1::6080"
    assert commands[1] == [engine, "port", "owned-viewer", "6080/tcp"]
    assert ("--network=slirp4netns" in commands[0]) == (engine == "podman")


@pytest.mark.parametrize("mode", ["human", "agent"])
def test_explicit_port_does_not_require_inspection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> None:
    docker = importlib.import_module("clawbench.runner.run_support.docker")
    monkeypatch.setattr(docker, "engine", lambda: "docker")
    commands: list[list[str]] = []
    monkeypatch.setattr(docker, "run", lambda cmd: commands.append(cmd))

    assert _start(docker, mode, tmp_path, host_port=6090) == 6090
    assert commands[0][commands[0].index("-p") + 1] == "6090:6080"
    assert len(commands) == 1


def test_remote_browser_publishes_no_viewer_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    docker = importlib.import_module("clawbench.runner.run_support.docker")
    monkeypatch.setattr(docker, "engine", lambda: "docker")
    commands: list[list[str]] = []
    monkeypatch.setattr(docker, "run", lambda cmd: commands.append(cmd))

    assert _start(docker, "agent", tmp_path, browser_mode="remote") is None
    assert "-p" not in commands[0]
    assert len(commands) == 1


@pytest.mark.parametrize(
    "mapping",
    [
        "",
        "0.0.0.0:49153",
        "127.0.0.1:0",
        "127.0.0.1:65536",
        "127.0.0.1:49153\n127.0.0.1:49154",
        "invalid",
    ],
)
def test_invalid_mapping_removes_only_just_started_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mapping: str
) -> None:
    docker = importlib.import_module("clawbench.runner.run_support.docker")
    monkeypatch.setattr(docker, "engine", lambda: "docker")
    commands: list[list[str]] = []

    def invoke(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=mapping)

    monkeypatch.setattr(docker.subprocess, "run", invoke)
    with pytest.raises(RuntimeError, match="viewer port"):
        _start(docker, "agent", tmp_path)
    assert [cmd[1] for cmd in commands] == ["run", "port", "rm"]
    assert commands[-1] == ["docker", "rm", "-f", "owned-viewer"]


@pytest.mark.parametrize("failure", ["daemon", "timeout", "missing-client"])
def test_failed_inspection_cleans_up_and_preserves_cause(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str
) -> None:
    docker = importlib.import_module("clawbench.runner.run_support.docker")
    monkeypatch.setattr(docker, "engine", lambda: "docker")
    commands: list[list[str]] = []
    error: Exception = {
        "daemon": subprocess.CalledProcessError(1, ["docker", "port"]),
        "timeout": subprocess.TimeoutExpired(["docker", "port"], 10),
        "missing-client": FileNotFoundError("synthetic client unavailable"),
    }[failure]

    def invoke(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        if cmd[1] == "port":
            raise error
        return subprocess.CompletedProcess(cmd, 0, stdout="")

    monkeypatch.setattr(docker.subprocess, "run", invoke)
    with pytest.raises(RuntimeError, match="viewer port") as caught:
        _start(docker, "human", tmp_path)
    assert caught.value.__cause__ is error
    assert commands[-1] == ["docker", "rm", "-f", "owned-viewer"]


def test_failed_start_does_not_remove_an_existing_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    docker = importlib.import_module("clawbench.runner.run_support.docker")
    monkeypatch.setattr(docker, "engine", lambda: "docker")
    commands: list[list[str]] = []

    def invoke(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        raise subprocess.CalledProcessError(125, cmd)

    monkeypatch.setattr(docker.subprocess, "run", invoke)
    with pytest.raises(subprocess.CalledProcessError):
        _start(docker, "agent", tmp_path)
    assert len(commands) == 1
    assert commands[0][1] == "run"


def test_cleanup_failure_does_not_hide_inspection_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    docker = importlib.import_module("clawbench.runner.run_support.docker")
    monkeypatch.setattr(docker, "engine", lambda: "docker")
    inspection_error = subprocess.CalledProcessError(1, ["docker", "port"])

    def invoke(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[1] == "port":
            raise inspection_error
        if cmd[1] == "rm":
            assert kwargs["timeout"] == 10
            raise subprocess.TimeoutExpired(cmd, 10)
        return subprocess.CompletedProcess(cmd, 0, stdout="")

    monkeypatch.setattr(docker.subprocess, "run", invoke)
    with pytest.raises(RuntimeError, match="viewer port") as caught:
        _start(docker, "agent", tmp_path)
    assert caught.value.__cause__ is inspection_error
    assert "Could not remove container owned-viewer" in inspection_error.__notes__[0]
