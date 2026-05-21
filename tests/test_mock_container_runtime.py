"""Container-helper tests backed by a pure-Python mock runtime."""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest


def _import_docker_helpers(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import docker helpers with a fake docker binary visible on PATH."""

    for module_name in (
        "clawbench.runner.run_support.docker",
        "clawbench.runner.run_support.config",
    ):
        sys.modules.pop(module_name, None)
    monkeypatch.delenv("CONTAINER_ENGINE", raising=False)
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: str(Path("mock-bin") / cmd) if cmd == "docker" else None,
    )
    return importlib.import_module("clawbench.runner.run_support.docker")


@dataclass
class MockContainerRuntime:
    commands: list[list[str]] = field(default_factory=list)

    def run(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        self.commands.append(list(cmd))
        stdout = ""
        if cmd[:3] == ["docker", "image", "inspect"] and "--format" in cmd:
            stdout = "sha256:mock-image\n"
        elif cmd == ["docker", "--version"]:
            stdout = "Docker version mock\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")


def test_mock_container_runtime_supports_engine_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker = _import_docker_helpers(monkeypatch)
    runtime = MockContainerRuntime()
    monkeypatch.setattr(docker.subprocess, "run", runtime.run)

    assert docker.image_exists("clawbench-openclaw") is True
    assert docker.image_id("clawbench-openclaw") == "sha256:mock-image"
    assert docker.container_engine_version() == "Docker version mock"
    assert runtime.commands == [
        ["docker", "image", "inspect", "clawbench-openclaw"],
        [
            "docker",
            "image",
            "inspect",
            "clawbench-openclaw",
            "--format",
            "{{.Id}}",
        ],
        ["docker", "--version"],
    ]


def test_docker_build_selects_base_and_harness_with_mock_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker = _import_docker_helpers(monkeypatch)
    build_calls: list[tuple[Path, str]] = []
    monkeypatch.setattr(docker, "image_exists", lambda _ref: False)
    monkeypatch.setattr(
        docker,
        "_build_one",
        lambda dockerfile, tag: build_calls.append((dockerfile, tag)),
    )

    docker.docker_build("codex")

    assert build_calls == [
        (docker.BASE_DOCKERFILE, "clawbench-base"),
        (docker._HARNESS_DOCKERFILES["codex"], "clawbench-codex"),
    ]


def test_docker_run_builds_agent_container_command_with_mock_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docker = _import_docker_helpers(monkeypatch)
    commands: list[list[str]] = []
    schema_path = tmp_path / "eval-schema.json"
    personal_info_dir = tmp_path / "my-info"
    schema_path.write_text("{}")
    personal_info_dir.mkdir()
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
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://localhost:8080")
    monkeypatch.setattr(docker, "run", lambda cmd: commands.append(cmd))

    docker.docker_run(
        "container-name",
        "Complete this task",
        schema_path,
        personal_info_dir,
        {
            "model": "provider/model",
            "base_url": "http://host.docker.internal:4000/v1",
            "api_type": "openai-completions",
            "api_key": "secret",
            "api_keys": ["secret"],
            "thinking_level": "medium",
            "temperature": 0.2,
            "max_tokens": 1234,
        },
        time_limit_s=60,
        host_port=6090,
        harness="codex",
    )

    cmd = commands[0]
    assert cmd[:5] == ["docker", "run", "-d", "--name", "container-name"]
    assert "-p" in cmd
    assert "6090:6080" in cmd
    assert "--add-host=host.docker.internal:host-gateway" in cmd
    assert f"{schema_path.resolve()}:/eval-schema.json:ro" in cmd
    assert f"{personal_info_dir.resolve()}:/my-info:ro" in cmd
    assert "HTTPS_PROXY=http://host.docker.internal:8080" in cmd
    assert "NO_PROXY=localhost,127.0.0.1" in cmd
    assert "MODEL_NAME=provider/model" in cmd
    assert "THINKING_LEVEL=medium" in cmd
    assert "TEMPERATURE=0.2" in cmd
    assert "MAX_TOKENS=1234" in cmd
    assert cmd[-1] == "clawbench-codex"


def test_docker_run_human_uses_podman_network_flags_with_mock_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docker = _import_docker_helpers(monkeypatch)
    commands: list[list[str]] = []
    schema_path = tmp_path / "eval-schema.json"
    personal_info_dir = tmp_path / "my-info"
    schema_path.write_text("{}")
    personal_info_dir.mkdir()
    monkeypatch.setattr(docker, "ENGINE", "podman")
    monkeypatch.setattr(docker, "run", lambda cmd: commands.append(cmd))

    docker.docker_run_human(
        "human-container",
        "Manual task",
        schema_path,
        personal_info_dir,
        time_limit_s=120,
        host_port=6091,
    )

    cmd = commands[0]
    assert cmd[:5] == ["podman", "run", "-d", "--name", "human-container"]
    assert "--network=slirp4netns" in cmd
    assert "HUMAN_MODE=1" in cmd
    assert "INSTRUCTION=Manual task" in cmd
    assert "TIME_LIMIT_S=120" in cmd
    assert "6091:6080" in cmd
    assert cmd[-1] == "clawbench-base"


def test_docker_copy_uses_mock_runtime_and_removes_stop_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docker = _import_docker_helpers(monkeypatch)
    commands: list[list[str]] = []
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    stop_marker = data_dir / ".stop-requested"
    stop_marker.write_text("stop")
    monkeypatch.setattr(docker, "run", lambda cmd: commands.append(cmd))

    docker.docker_copy("container-name", tmp_path)

    assert commands == [
        ["docker", "cp", "container-name:/data", str(tmp_path / "data")]
    ]
    assert not stop_marker.exists()
