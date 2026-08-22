"""Regression tests for the Harbor ClawBench Kernel control arm."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path

import pytest

from clawbench.eval.harbor_adapter import (
    PLAYWRIGHT_MCP_PACKAGE,
    PLAYWRIGHT_MCP_VERSION,
    main as adapt_main,
    write_harbor_task,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
KERNEL_BROWSER_SCRIPT = (
    REPO_ROOT / "src" / "clawbench" / "runtime" / "harbor" / "kernel-browser.py"
)


def _task() -> dict:
    return {
        "metadata": {
            "task_id": 1134,
            "description": "Find nearest Red Cross chapter",
        },
        "instruction": "Find the nearest Red Cross chapter to zip code 90210.",
        "eval_schema": {"url_pattern": "redcross\\.org/chapter", "method": "GET"},
        "time_limit": 30,
        "extra_info": [],
    }


@pytest.fixture()
def adapted_kernel_task(tmp_path: Path) -> Path:
    case = tmp_path / "case"
    case.mkdir()
    (case / "task.json").write_text(json.dumps(_task()))
    return write_harbor_task(
        task_dir=case,
        task=_task(),
        output_root=tmp_path / "out",
        output_name="v2-1134-chapter-finder-redcross",
        org="clawbench",
        dataset_name="v2",
        browser_runtime="kernel",
    )


def test_redcross_task_intercepts_zip_lookup_not_chapter_finder_page() -> None:
    task_path = (
        REPO_ROOT
        / "test-cases"
        / "v2"
        / "v2-1134-chapter-finder-redcross"
        / "task.json"
    )
    schema = json.loads(task_path.read_text())["eval_schema"]

    assert not re.search(
        schema["url_pattern"],
        "https://www.redcross.org/find-your-local-chapter.html",
    )
    assert re.search(
        schema["url_pattern"],
        "https://www.redcross.org/api/lookup/v1/region-mappings/90210?type=RCO",
    )
    assert schema["params"] == {"type": "RCO"}


def test_kernel_runtime_selection_writes_bridge_env_and_pinned_mcp(
    adapted_kernel_task: Path,
) -> None:
    config = tomllib.loads((adapted_kernel_task / "task.toml").read_text())

    assert config["metadata"]["browser_runtime"] == "kernel"
    env = config["environment"]["env"]
    assert env["CLAWBENCH_HARBOR_BROWSER_RUNTIME"] == "kernel"
    assert env["PLAYWRIGHT_CDP_URL"] == "http://127.0.0.1:7878"
    assert env["CLAWBENCH_CDP_URL"] == "http://127.0.0.1:7878"
    assert env["CLAWBENCH_RECORDING_MODE"] == "provider-download"
    assert env["KERNEL_API_KEY"] == "${KERNEL_API_KEY}"

    servers = config["environment"]["mcp_servers"]
    assert len(servers) == 1
    server = servers[0]
    assert server["name"] == "playwright"
    assert server["transport"] == "stdio"
    assert server["command"] == "npx"
    assert server["args"][0] == "-y"
    # Pinned package so the control arm is reproducible.
    assert server["args"][1] == f"{PLAYWRIGHT_MCP_PACKAGE}@{PLAYWRIGHT_MCP_VERSION}"
    assert "--cdp-endpoint" in server["args"]
    assert "http://127.0.0.1:7878" in server["args"]

    healthcheck = config["steps"][0]["healthcheck"]["command"]
    assert "7878/json/version" in healthcheck


def test_kernel_setup_and_test_scripts_wire_lifecycle(
    adapted_kernel_task: Path,
) -> None:
    workdir = adapted_kernel_task / "steps" / "run" / "workdir"
    tests = adapted_kernel_task / "steps" / "run" / "tests"

    setup = (workdir / "setup.sh").read_text()
    assert "kernel-browser.py start" in setup
    assert "export CLAWBENCH_BROWSER_CDP_URL_FILE=" in setup
    assert "trap cleanup_browser EXIT" in setup
    assert "kernel-browser.py cleanup" in setup
    assert "127.0.0.1:7878/json/version" in setup

    test = (tests / "test.sh").read_text()
    assert "kernel-browser.py finalize" in test

    env_dir = adapted_kernel_task / "environment"
    assert (env_dir / "harbor" / "kernel-browser.py").is_file()
    assert (env_dir / "harbor" / "browser_runtime_providers.py").is_file()


def test_local_runtime_default_has_no_kernel_hooks(tmp_path: Path) -> None:
    case = tmp_path / "case"
    case.mkdir()
    (case / "task.json").write_text(json.dumps(_task()))
    out = write_harbor_task(
        task_dir=case,
        task=_task(),
        output_root=tmp_path / "out",
        output_name="local",
        org="clawbench",
        dataset_name="v2",
    )

    config = tomllib.loads((out / "task.toml").read_text())
    assert config["metadata"]["browser_runtime"] == "local"
    assert "mcp_servers" not in config["environment"]
    assert config["environment"]["env"]["PLAYWRIGHT_CDP_URL"] == "http://127.0.0.1:9223"
    assert config["environment"]["env"].get("CLAWBENCH_HARBOR_BROWSER_RUNTIME") is None

    setup = (out / "steps" / "run" / "workdir" / "setup.sh").read_text()
    assert "kernel-browser" not in setup
    assert (out / "environment" / "harbor" / "browser_runtime_providers.py").is_file()


def test_instruction_ports_native_restrictions(adapted_kernel_task: Path) -> None:
    instruction = (adapted_kernel_task / "steps" / "run" / "instruction.md").read_text()
    # Native ClawBench prompt text (source of truth) survives verbatim.
    assert "entirely through the browser" in instruction
    assert "Do NOT use command-line tools, scripts, or direct API/SMTP calls" in (
        instruction
    )
    # Ported harness restrictions.
    assert "Time limit: 30 minutes" in instruction
    assert "Playwright MCP browser tools" in instruction
    assert "Do NOT make direct HTTP/network requests" in instruction
    assert "Submit through the browser" in instruction
    assert "Stop after submission" in instruction
    # Credential-free bridge endpoint, never a provider URL.
    assert "http://127.0.0.1:7878" in instruction
    assert "ws://" not in instruction


def test_adapter_cli_rejects_invalid_runtime_options_json(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        adapt_main(
            [
                "--output-dir",
                str(tmp_path / "out"),
                "--limit",
                "1",
                "--overwrite",
                "--browser-runtime",
                "kernel",
                "--browser-runtime-options",
                "not-json",
            ]
        )
    assert excinfo.value.code == 2


def test_adapter_cli_bakes_runtime_options_into_task_toml(
    tmp_path: Path,
) -> None:
    adapt_main(
        [
            "--output-dir",
            str(tmp_path / "out"),
            "--limit",
            "1",
            "--overwrite",
            "--browser-runtime",
            "kernel",
            "--browser-runtime-options",
            '{"stealth": true}',
        ]
    )
    task_toml = next((tmp_path / "out").glob("*/task.toml"))
    config = tomllib.loads(task_toml.read_text())
    assert config["environment"]["env"]["CLAWBENCH_BROWSER_RUNTIME_OPTIONS"] == (
        '{"stealth": true}'
    )


# ---------------------------------------------------------------------------
# kernel-browser.py lifecycle script
# ---------------------------------------------------------------------------


def _load_kernel_browser_module(monkeypatch: pytest.MonkeyPatch, home: Path):
    spec = importlib.util.spec_from_file_location(
        "kernel_browser_under_test", KERNEL_BROWSER_SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "STATE_DIR", home / "clawbench-run")
    monkeypatch.setattr(
        module, "STATE_FILE", home / "clawbench-run" / "kernel-browser-state.json"
    )
    monkeypatch.setattr(
        module, "CDP_URL_FILE", home / "clawbench-run" / "kernel-cdp-url"
    )
    monkeypatch.setattr(
        module, "METADATA_FILE", home / "my-info" / "kernel_browser.json"
    )
    monkeypatch.setattr(
        module, "LIFECYCLE_FILE", home / "data" / "kernel-browser-lifecycle.json"
    )
    monkeypatch.setattr(module, "TASK_FILE", home / "task.json")
    monkeypatch.setattr(module, "DATA_DIR", home / "data")
    sys.modules[spec.name] = module
    return module


class FakeSession:
    def __init__(self) -> None:
        from clawbench.runner.run_support.browser_runtime.providers import (
            BrowserSession,
        )

        self._session = BrowserSession(
            provider="kernel",
            mode="remote",
            session_id="sess-123",
            cdp_url="wss://kernel.example/browser/sess-123/cdp?token=secret-token",
            viewer_url="https://kernel.example/live/sess-123",
            viewer_url_sensitive=True,
            metadata={
                "replay_id": "replay-9",
                "region": "us-east",
                "stealth": False,
            },
            recording_mode="provider-download",
        )

    def __getattr__(self, name: str):
        return getattr(self._session, name)


class FakeProvider:
    name = "kernel"

    def __init__(self, fail_cleanup: bool = False) -> None:
        self.fail_cleanup = fail_cleanup
        self.finalize_calls = 0
        self.cleanup_calls = 0
        self.exists_calls: list[str] = []
        self.deleted = False

    def start(self, task: dict, time_limit_s: int) -> FakeSession:
        assert time_limit_s == 1800
        return FakeSession()

    def finalize(self, session: FakeSession, output_dir: Path) -> None:
        self.finalize_calls += 1
        recording = Path(output_dir) / "data" / "recording.mp4"
        recording.parent.mkdir(parents=True, exist_ok=True)
        recording.write_bytes(b"mp4-bytes")
        session.metadata["recording_bytes"] = len(b"mp4-bytes")

    def cleanup(self, session: FakeSession) -> None:
        self.cleanup_calls += 1
        if self.fail_cleanup:
            from clawbench.runner.run_support.browser_runtime.providers import (
                BrowserRuntimeError,
            )

            raise BrowserRuntimeError("delete failed")
        self.deleted = True

    def session_exists(self, session_id: str) -> bool:
        self.exists_calls.append(session_id)
        return not self.deleted


@pytest.fixture()
def kernel_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "task.json").write_text(json.dumps(_task()))
    for var in (
        "KERNEL_API_KEY",
        "KERNEL_BASE_URL",
        "CLAWBENCH_BROWSER_RUNTIME_OPTIONS",
    ):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_start_writes_state_and_credential_free_metadata(
    kernel_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KERNEL_API_KEY", "k-test-key")
    module = _load_kernel_browser_module(monkeypatch, kernel_env)
    provider = FakeProvider()
    monkeypatch.setattr(module, "_load_provider", lambda: provider)

    assert module.cmd_start() == 0

    state = json.loads(module.STATE_FILE.read_text())
    assert state["status"] == "created"
    assert state["cdp_url"].startswith("wss://kernel.example")
    assert oct(module.STATE_FILE.stat().st_mode & 0o777) == "0o600"
    assert oct(module.CDP_URL_FILE.stat().st_mode & 0o777) == "0o600"

    metadata = json.loads(module.METADATA_FILE.read_text())
    assert metadata["session_id"] == "sess-123"
    assert metadata["replay_id"] == "replay-9"
    assert metadata["stealth"] is False
    assert metadata["cdp_bridge_url"] == "http://127.0.0.1:7878"
    blob = module.METADATA_FILE.read_text()
    assert "k-test-key" not in blob
    assert "secret-token" not in blob


def test_finalize_downloads_recording_deletes_browser_and_is_idempotent(
    kernel_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_kernel_browser_module(monkeypatch, kernel_env)
    provider = FakeProvider()
    monkeypatch.setattr(module, "_load_provider", lambda: provider)
    assert module.cmd_start() == 0

    assert module.cmd_finalize() == 0

    recording = kernel_env / "data" / "recording.mp4"
    assert recording.read_bytes() == b"mp4-bytes"
    lifecycle = json.loads(module.LIFECYCLE_FILE.read_text())
    assert lifecycle["status"] == "deleted"
    assert lifecycle["deletion_verified"] is True
    assert provider.cleanup_calls == 1
    assert provider.exists_calls == ["sess-123"]

    # Idempotent rerun makes no further API calls.
    assert module.cmd_finalize() == 0
    assert provider.cleanup_calls == 1


def test_finalize_reports_failure_when_cleanup_fails(
    kernel_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_kernel_browser_module(monkeypatch, kernel_env)
    provider = FakeProvider(fail_cleanup=True)
    monkeypatch.setattr(module, "_load_provider", lambda: provider)
    assert module.cmd_start() == 0

    assert module.cmd_finalize() == 1
    state = json.loads(module.STATE_FILE.read_text())
    assert state["cleanup_error"] == "delete failed"


def test_cleanup_recovers_from_agent_visible_metadata_alone(
    kernel_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_kernel_browser_module(monkeypatch, kernel_env)
    provider = FakeProvider()
    monkeypatch.setattr(module, "_load_provider", lambda: provider)
    assert module.cmd_start() == 0
    module.STATE_FILE.unlink()

    assert module.cmd_cleanup() == 0
    assert provider.cleanup_calls == 1
    lifecycle = json.loads(module.LIFECYCLE_FILE.read_text())
    assert lifecycle["status"] == "deleted"
    assert lifecycle["deletion_verified"] is True


def test_commands_are_noops_without_a_created_browser(
    kernel_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_kernel_browser_module(monkeypatch, kernel_env)
    provider = FakeProvider()
    monkeypatch.setattr(module, "_load_provider", lambda: provider)

    assert module.cmd_finalize() == 0
    assert module.cmd_cleanup() == 0
    assert provider.cleanup_calls == 0


def test_kernel_session_exists_reports_404_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clawbench.runner.run_support.browser_runtime.providers import (
        KernelRuntimeProvider,
        _KernelApiError,
    )

    provider = KernelRuntimeProvider(api_key="k", options={})

    def fake_request(method: str, path: str, payload=None) -> bytes:
        raise _KernelApiError("not found", status=404)

    monkeypatch.setattr(provider, "_request", fake_request)
    assert provider.session_exists("gone") is False

    def ok_request(method: str, path: str, payload=None) -> bytes:
        if method == "GET":
            return b"{}"
        raise AssertionError(method)

    monkeypatch.setattr(provider, "_request", ok_request)
    assert provider.session_exists("alive") is True


def test_finalize_still_deletes_browser_when_replay_download_fails(
    kernel_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from clawbench.runner.run_support.browser_runtime.providers import (
        BrowserRuntimeError,
    )

    module = _load_kernel_browser_module(monkeypatch, kernel_env)
    provider = FakeProvider()
    monkeypatch.setattr(module, "_load_provider", lambda: provider)

    def failing_finalize(session, output_dir):  # noqa: ANN001
        raise BrowserRuntimeError("replay stuck processing")

    monkeypatch.setattr(provider, "finalize", failing_finalize)
    assert module.cmd_start() == 0

    assert module.cmd_finalize() == 0
    lifecycle = json.loads(module.LIFECYCLE_FILE.read_text())
    assert lifecycle["status"] == "deleted"
    assert lifecycle["deletion_verified"] is True
    assert "replay finalization failed" in lifecycle["cleanup_error"]
    assert provider.cleanup_calls == 1
